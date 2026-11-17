import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import chess
import httpx2
import pytest
from openai import AsyncOpenAI, RateLimitError

from backend.coach import (
    Coach, CoachConfigurationError, CoachPosition, CoachResponseError,
    CoachSettings, InvalidPositionError, build_request, open_coach,
)
from backend.coach.service import SYSTEM_PROMPT_PATH


def completed_response(**overrides):
    return {
        "id": "resp_test", "object": "response", "created_at": 1,
        "status": "completed", "model": "gpt-6-astra", "error": None,
        "incomplete_details": None,
        "output": [
            {"type": "reasoning", "id": "rs_test", "summary": []},
            {"type": "message", "id": "msg_test", "role": "assistant", "status": "completed",
             "content": [{"type": "output_text", "text": "### 1. Understand the Position\nTest analysis.\n\n### 2. Develop a Plan\nTest plan.", "annotations": []}]},
        ],
        "usage": {"input_tokens": 120, "output_tokens": 40, "total_tokens": 160,
                  "input_tokens_details": {"cached_tokens": 0},
                  "output_tokens_details": {"reasoning_tokens": 20}},
        **overrides,
    }


def analyze_with_transport(handler, fen=chess.STARTING_FEN, **kwargs):
    async def run():
        async with AsyncOpenAI(
            api_key="test-key", base_url="https://api.openai.com/v1", max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        ) as client:
            return await Coach(client).analyze(fen, **kwargs)
    return asyncio.run(run())


def test_responses_request_and_output_through_real_sdk():
    received = []
    board = chess.Board()
    board.push_uci("e2e4")
    fen = board.fen(en_passant="fen")

    def upstream(request):
        assert request.method == "POST"
        assert str(request.url) == "https://api.openai.com/v1/responses"
        body = json.loads(request.content)
        received.append(body)
        assert body["model"] == "gpt-6-astra"
        assert body["reasoning"] == {"effort": "xhigh"}
        assert body["store"] is False
        assert body["max_output_tokens"] == 32768
        assert set(body) == {"model", "reasoning", "input", "max_output_tokens", "store"}
        assert body["input"][0] == {"role": "system", "content": SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")}
        message = body["input"][1]
        assert message["role"] == "user"
        assert fen in message["content"]  # Includes the e3 en-passant target.
        assert "for Black, the side to move" in message["content"]
        assert "8  r n b q k b n r" in message["content"]
        assert "4  . . . . P . . ." in message["content"]
        assert "1  R N B Q K B N R" in message["content"]
        assert "a b c d e f g h" in message["content"]
        return httpx2.Response(200, json=completed_response())

    result = analyze_with_transport(upstream, fen)
    assert len(received) == 1
    assert result.response_id == "resp_test"
    assert result.position.fen == fen
    assert result.text == completed_response()["output"][1]["content"][0]["text"]
    assert result.usage["output_tokens_details"]["reasoning_tokens"] == 20


@pytest.mark.parametrize("fen", ["", "not a fen", chess.STARTING_BOARD_FEN, "8/8/8/8/8/8/8/8 w - - 0 1"])
def test_invalid_positions_never_reach_openai(fen):
    def unexpected_request(request):
        pytest.fail("An invalid position must not create a paid request")
    with pytest.raises(InvalidPositionError):
        analyze_with_transport(unexpected_request, fen)


def test_supplied_ascii_must_match_fen():
    position = CoachPosition.from_fen(chess.STARTING_FEN)
    for ascii_board in (position.ascii_board, str(chess.Board())):
        assert CoachPosition.from_fen(chess.STARTING_FEN, ascii_board=ascii_board) == position
    with pytest.raises(InvalidPositionError, match="ASCII board must match"):
        build_request(chess.STARTING_FEN, ascii_board=position.ascii_board.replace("r n b q k b n r", ". n b q k b n r"))


@pytest.mark.parametrize("response, message", [
    (completed_response(status="incomplete", incomplete_details={"reason": "max_output_tokens"}), "max_output_tokens"),
    (completed_response(status="failed", output=[]), "failed"),
    (completed_response(output=[]), "empty"),
    (completed_response(output=[{"type": "message", "id": "msg_test", "role": "assistant", "status": "completed", "content": [{"type": "refusal", "refusal": "Cannot answer."}]}]), "declined"),
])
def test_incomplete_empty_and_refused_outputs_are_not_success(response, message):
    with pytest.raises(CoachResponseError, match=message) as error:
        analyze_with_transport(lambda request: httpx2.Response(200, json=response))
    assert error.value.response_id == "resp_test"


def test_api_errors_propagate_without_fabricated_analysis_or_retry():
    requests = []
    def upstream(request):
        requests.append(request)
        return httpx2.Response(429, json={"error": {"message": "Rate limited", "type": "rate_limit_error"}})
    with pytest.raises(RateLimitError):
        analyze_with_transport(upstream)
    assert len(requests) == 1


def test_missing_key_is_lazy_and_actionable(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert build_request(chess.STARTING_FEN)["model"] == "gpt-6-astra"
    async def run():
        async with open_coach():
            pytest.fail("A client must not be created without a key")
    with pytest.raises(CoachConfigurationError, match="OPENAI_API_KEY"):
        asyncio.run(run())


@pytest.mark.parametrize("name,value", [("COACH_MAX_OUTPUT_TOKENS", "0"), ("COACH_MAX_OUTPUT_TOKENS", "abc"), ("COACH_TIMEOUT_SECONDS", "nan"), ("COACH_TIMEOUT_SECONDS", "-1")])
def test_invalid_environment_settings(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(CoachConfigurationError):
        CoachSettings.from_env()


def test_model_settings_are_scoped_and_preserve_runtime_limits(monkeypatch):
    monkeypatch.setenv("COACH_MAX_OUTPUT_TOKENS", "4096")
    monkeypatch.setenv("COACH_TIMEOUT_SECONDS", "45")
    terra = CoachSettings.from_env(model="gpt-6.1-terra")
    assert terra.max_output_tokens == 4096 and terra.timeout_seconds == 45
    request = build_request(chess.STARTING_FEN, settings=terra)
    assert request["model"] == "gpt-6.1-terra"
    assert request["reasoning"] == {"effort": "xhigh"}
    assert CoachSettings.from_env().model == CoachSettings().model == "gpt-6-astra"
    with pytest.raises(CoachConfigurationError, match="Unsupported coach model"):
        CoachSettings(model="unknown-model")


def test_cli_dry_run_without_credentials():
    env = {k: v for k, v in os.environ.items() if not k.startswith(("OPENAI_", "COACH_"))}
    result = subprocess.run(
        [sys.executable, "-m", "backend.coach", "--fen", chess.STARTING_FEN, "--dry-run"],
        cwd=Path(__file__).resolve().parents[2], env=env, text=True, encoding="utf-8",
        # Cold SDK imports on Windows can exceed 15 seconds. This checks the
        # request contract and absence of network use, not startup latency.
        capture_output=True, timeout=60 if sys.platform == "win32" else 15,
    )
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body["reasoning"]["effort"] == "xhigh"
    assert body["input"][0]["role"] == "system"
    assert chess.STARTING_FEN in body["input"][1]["content"]
