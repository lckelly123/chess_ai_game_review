import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import Mock

import chess
import httpx
import httpx2
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from openai import AsyncOpenAI

from backend.coach import Coach, CoachAnalysis, CoachPosition
from backend.coach.routes import create_coach_router
from backend.main import create_app
from backend.database import Database
from backend.tests.test_coach import completed_response
from backend.tests.position_fixtures import position_evidence


def mock_coach_factory(handler, *, engine=None):
    @asynccontextmanager
    async def factory(settings):
        async with AsyncOpenAI(
            api_key="test-key", max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        ) as client:
            yield Coach(client, settings, engine=engine, position_engine=position_evidence)
    return factory


@pytest.mark.parametrize("model", [None, "gpt-6-astra", "gpt-6.1-terra"])
def test_coach_endpoint_calls_responses_with_only_selected_position(test_db_url, model):
    requests = []
    board = chess.Board()
    board.push_san("e4")
    fen = board.fen()
    def upstream(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["model"] == (model or "gpt-6-astra")
        assert body["reasoning"] == {"effort": "medium"}
        assert fen in body["input"][1]["content"]
        assert "for Black" in body["input"][1]["content"]
        assert "ASCII board" in body["input"][1]["content"]
        return httpx2.Response(200, json=completed_response(request=request, model=body["model"]))
    app = create_app(test_db_url, coach_factory=mock_coach_factory(upstream))
    with TestClient(app) as client:
        response = client.post("/api/coach/analyze", json={"fen": fen, **({"model": model} if model else {})})
        assert response.status_code == 200
        result = response.json()
        assert result["fen"] == fen
        assert result["model"] == (model or "gpt-6-astra")
        assert result["text"].startswith("### 1. Understand the Position")
        assert set(result) == {"fen", "played_move", "text", "model", "response_id", "created_at", "stockfish", "teaching", "candidate_san", "position_evidence", "classification_version", "classification_current", "sharpness_version", "sharpness_current", "telemetry_classification"}
        assert result["sharpness_current"] is True
        assert result["position_evidence"] == position_evidence(fen)
        assert result["teaching"]["candidate_moves"][0]["uci"] == "g8h6"
        assert result["candidate_san"] == {"g8h6": "Nh6"}
        assert result["stockfish"] is None
        assert len(requests) == 1
        # Question content cannot silently become part of a paid request.
        assert client.post("/api/coach/analyze", json={"fen": fen, "question": "What now?"}).status_code == 422
        assert client.post("/api/coach/analyze", json={"fen": "invalid"}).status_code == 422
        for invalid_model in ("unknown-model", "", None, 42):
            assert client.post("/api/coach/analyze", json={"fen": fen, "model": invalid_model}).status_code == 422
        assert len(requests) == 1


@pytest.mark.parametrize("mode,passes", [("position", 1), ("move", 1), ("final", 1)])
def test_model_selection_does_not_leak_into_later_requests(mode, passes):
    models = []
    saved = []

    def save_feedback(result):
        saved.append(result)
        return {"fen": result.position.fen, "played_move": result.played_move,
                "text": result.text, "model": result.model, "response_id": result.response_id,
                "created_at": datetime.now(timezone.utc)}

    def upstream(request):
        assert str(request.url) == "https://api.openai.com/v1/responses"
        model = json.loads(request.content)["model"]
        assert json.loads(request.content)["reasoning"] == {"effort": "medium"}
        models.append(model)
        return httpx2.Response(200, json=completed_response(request=request, model=model))

    # Exercise the HTTP -> settings -> graph -> SDK boundary independently of
    # PostgreSQL; the integration tests below verify durable storage separately.
    app = FastAPI()
    app.state.db = Mock()
    app.state.db.game.return_value = {"pgn": '[White "alice"]\n[Black "bob"]\n[Result "1-0"]\n\n1. e4 e5 1-0'}
    app.state.db.save_coach_feedback.side_effect = save_feedback

    def engine(review, position):
        assert mode == "move"
        return {"fen": review.position.fen, "perspective": review.position.side_to_move,
                "played_move": {"uci": review.played_move_uci}}

    app.include_router(create_coach_router(mock_coach_factory(upstream, engine=engine)))
    payload = {"fen": chess.STARTING_FEN} if mode == "position" else {"game_id": "test-game", "ply": 0 if mode == "move" else 2}
    with TestClient(app) as client:
        for selection in ({"model": "gpt-6.1-terra"}, {}, {"model": "gpt-6-astra"}):
            result = client.post("/api/coach/analyze", json={**payload, **selection})
            assert result.status_code == 200
            assert result.json()["model"] == selection.get("model", "gpt-6-astra")
            assert result.json()["played_move"] == ("e2e4" if mode == "move" else None)
        assert models == ["gpt-6.1-terra"] * passes + ["gpt-6-astra"] * (2 * passes)
        assert [answer.model for answer in saved] == ["gpt-6.1-terra", "gpt-6-astra", "gpt-6-astra"]
        for invalid_model in ("unknown-model", "", None, 42):
            assert client.post("/api/coach/analyze", json={**payload, "model": invalid_model}).status_code == 422
        assert len(models) == 3 * passes and len(saved) == 3


@pytest.mark.parametrize("model", ["gpt-6-astra", "gpt-6.1-terra"])
@pytest.mark.parametrize("status,expected,phrase", [
    (401, 503, "API key"), (403, 502, "model access"),
    (404, 502, "model access"), (429, 429, "quota"), (500, 502, "try again"),
])
def test_coach_endpoint_reports_safe_provider_errors(status, expected, phrase, model):
    app = FastAPI()
    app.state.db = Mock()
    app.include_router(create_coach_router(mock_coach_factory(
        lambda request: httpx2.Response(status, json={"error": {"message": "sensitive-provider-detail", "type": "api_error"}})
    )))
    with TestClient(app) as client:
        response = client.post("/api/coach/analyze", json={"fen": chess.STARTING_FEN, "model": model})
        assert response.status_code == expected
        assert phrase in response.json()["detail"]
        assert "sensitive-provider-detail" not in response.text
        if status in (403, 404):
            assert model in response.json()["detail"]
        app.state.db.save_coach_feedback.assert_not_called()


def test_coach_timeout_and_incomplete_answer(test_db_url):
    def timeout(request):
        raise httpx2.ReadTimeout("upstream-timeout", request=request)
    for handler, status in (
        (timeout, 504),
        (lambda request: httpx2.Response(200, json=completed_response(status="incomplete", incomplete_details={"reason": "max_output_tokens"})), 502),
    ):
        app = create_app(test_db_url, coach_factory=mock_coach_factory(handler))
        with TestClient(app) as client:
            response = client.post("/api/coach/analyze", json={"fen": chess.STARTING_FEN})
            assert response.status_code == status
            assert "Test analysis" not in response.text
            assert client.get("/api/coach/feedback", params={"fen": chess.STARTING_FEN}).json() is None


def test_missing_key_does_not_break_library(test_db_url, monkeypatch):
    # An explicit empty value prevents loading real credentials from local .env.
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with TestClient(create_app(test_db_url)) as client:
        assert client.get("/api/health").status_code == 200
        response = client.post("/api/coach/analyze", json={"fen": chess.STARTING_FEN})
        assert response.status_code == 503
        assert "OPENAI_API_KEY" in response.json()["detail"]


def test_local_dotenv_loads_without_overriding_process_environment(test_db_url, tmp_path, monkeypatch):
    import backend.main as main
    monkeypatch.setattr(main, "ROOT", tmp_path)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=dotenv-test-key\nCOACH_TIMEOUT_SECONDS=42\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("COACH_TIMEOUT_SECONDS", "15")
    with TestClient(create_app(test_db_url)) as client:
        import os
        assert os.environ["OPENAI_API_KEY"] == "dotenv-test-key"
        assert os.environ["COACH_TIMEOUT_SECONDS"] == "15"
        assert client.get("/api/health").status_code == 200


def test_overlapping_coach_requests_are_rejected(test_db_url):
    async def run():
        started, finish = asyncio.Event(), asyncio.Event()
        calls = []
        class SlowCoach:
            async def analyze(self, fen):
                calls.append(fen)
                started.set()
                await finish.wait()
                return CoachAnalysis("Test response", "resp_test", "gpt-6-astra", CoachPosition.from_fen(fen), None)
        @asynccontextmanager
        async def factory(settings):
            yield SlowCoach()
        app = create_app(test_db_url, coach_factory=factory)
        app.state.db = Database(test_db_url)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            first = asyncio.create_task(client.post("/api/coach/analyze", json={"fen": chess.STARTING_FEN}))
            try:
                await asyncio.wait_for(started.wait(), timeout=3)
                second = await client.post("/api/coach/analyze", json={"fen": chess.STARTING_FEN})
                assert second.status_code == 409
                assert len(calls) == 1
            finally:
                finish.set()
            assert (await first).status_code == 200
    asyncio.run(run())
