import asyncio
import json
from contextlib import asynccontextmanager

import chess
import httpx
import httpx2
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI

from backend.coach import Coach, CoachAnalysis, CoachPosition
from backend.main import create_app
from backend.database import Database
from backend.tests.test_coach import completed_response


def mock_coach_factory(handler):
    @asynccontextmanager
    async def factory():
        async with AsyncOpenAI(
            api_key="test-key", max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        ) as client:
            yield Coach(client)
    return factory


def test_coach_endpoint_calls_responses_with_only_selected_position(test_db_url):
    requests = []
    board = chess.Board()
    board.push_san("e4")
    fen = board.fen()
    def upstream(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["model"] == "gpt-6-astra"
        assert body["reasoning"] == {"effort": "xhigh"}
        assert fen in body["input"][1]["content"]
        assert "for Black" in body["input"][1]["content"]
        assert "ASCII board" in body["input"][1]["content"]
        return httpx2.Response(200, json=completed_response())
    app = create_app(test_db_url, coach_factory=mock_coach_factory(upstream))
    with TestClient(app) as client:
        response = client.post("/api/coach/analyze", json={"fen": fen})
        assert response.status_code == 200
        result = response.json()
        assert result["fen"] == fen
        assert result["text"].startswith("### 1. Understand the Position")
        assert set(result) == {"fen", "text", "model", "response_id", "created_at"}
        assert len(requests) == 1
        # Question content cannot silently become part of a paid request.
        assert client.post("/api/coach/analyze", json={"fen": fen, "question": "What now?"}).status_code == 422
        assert client.post("/api/coach/analyze", json={"fen": "invalid"}).status_code == 422
        assert len(requests) == 1


@pytest.mark.parametrize("status,expected,phrase", [
    (401, 503, "API key"), (403, 502, "model access"),
    (404, 502, "model access"), (429, 429, "quota"), (500, 502, "try again"),
])
def test_coach_endpoint_reports_safe_provider_errors(test_db_url, status, expected, phrase):
    app = create_app(test_db_url, coach_factory=mock_coach_factory(
        lambda request: httpx2.Response(status, json={"error": {"message": "sensitive-provider-detail", "type": "api_error"}})
    ))
    with TestClient(app) as client:
        response = client.post("/api/coach/analyze", json={"fen": chess.STARTING_FEN})
        assert response.status_code == expected
        assert phrase in response.json()["detail"]
        assert "sensitive-provider-detail" not in response.text


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
        async def factory():
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
