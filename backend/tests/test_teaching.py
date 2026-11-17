import asyncio
import json
from copy import deepcopy
from unittest.mock import Mock

import chess
import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.coach import Coach, CoachResponseError
from backend.coach.routes import create_coach_router
from backend.coach.teaching import TeachingAnalysis
from backend.tests.test_coach import analyze_with_transport, completed_response, teaching_output
from backend.tests.test_coach_graph import mock_client
from backend.tests.test_coach_routes import mock_coach_factory


def response_with(data):
    result = completed_response()
    result["output"][1]["content"][0]["text"] = json.dumps(data) if isinstance(data, dict) else data
    return result


@pytest.mark.parametrize("fen,uci,san", [
    (chess.STARTING_FEN, "e2e4", "e4"),
    ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1", "O-O"),
    ("r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1", "e8c8", "O-O-O"),
    ("7k/P7/8/8/8/8/8/7K w - - 0 1", "a7a8n", "a8=N"),
    ("7k/8/8/3pP3/8/8/8/K7 w - d6 0 2", "e5d6", "exd6"),
])
def test_legal_candidates_include_castling_promotion_and_en_passant(fen, uci, san):
    data = teaching_output(fen)
    data["candidate_moves"] = [{"uci": uci, "reason": "A concrete instructional reason.", "highlight_squares": ["e4", "d5"]}]
    result = analyze_with_transport(lambda request: httpx2.Response(200, json=response_with(data)), fen)
    assert result.position_analysis["structured"] == data
    assert TeachingAnalysis.model_validate(data).candidate_san(fen) == {uci: san}


@pytest.mark.parametrize("fen", [
    "7k/6Q1/6K1/8/8/8/8/8 b - - 0 1",  # Checkmate.
    "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1",  # Stalemate.
])
def test_no_legal_moves_accepts_empty_candidates_without_second_pass(fen):
    requests = []
    def upstream(request):
        requests.append(request)
        return httpx2.Response(200, json=completed_response(fen=fen))
    result = analyze_with_transport(upstream, fen)
    assert len(requests) == 1
    assert result.position_analysis["structured"]["candidate_moves"] == []
    assert result.move_analysis is None and result.stockfish is None


def invalid_outputs():
    baseline = teaching_output()
    yield "not JSON"
    yield "```json\n" + json.dumps(baseline) + "\n```"
    for key, value in [("position_character", "winning"), ("positional_thesis", " "),
                       ("needs_of_position", ""), ("candidate_moves", []), ("extra", "field")]:
        yield {**baseline, key: value}
    for key, value in [("uci", "e7e5"), ("uci", "e1g1"), ("uci", "e2e5"), ("uci", "0000"),
                       ("uci", "g1h3q"), ("reason", " "), ("highlight_squares", ["a1"]),
                       ("highlight_squares", ["a1", "a2", "a3"]), ("highlight_squares", ["a1", "a1"]),
                       ("highlight_squares", ["a1", "a9"]), ("arrow", ["a1", "a2"])]:
        data = deepcopy(baseline)
        data["candidate_moves"][0][key] = value
        yield data
    yield {**baseline, "candidate_moves": baseline["candidate_moves"] * 2}
    yield {**baseline, "candidate_moves": baseline["candidate_moves"] * 4}


@pytest.mark.parametrize("data", list(invalid_outputs()))
def test_invalid_teaching_never_reaches_engine_or_second_call(data):
    calls = []
    def upstream(request):
        calls.append(request)
        return httpx2.Response(200, json=response_with(data))
    engine = Mock(side_effect=AssertionError("Invalid candidates must stop the graph"))
    async def run():
        async with mock_client(upstream) as client:
            with pytest.raises(CoachResponseError, match="invalid position teaching"):
                await Coach(client, engine=engine).analyze(chess.STARTING_FEN, played_move="e2e4")
    asyncio.run(run())
    assert len(calls) == 1
    engine.assert_not_called()


def test_invalid_teaching_is_not_saved():
    app = FastAPI()
    app.state.db = Mock()
    app.include_router(create_coach_router(mock_coach_factory(
        lambda request: httpx2.Response(200, json=response_with({**teaching_output(), "candidate_moves": []}))
    )))
    with TestClient(app) as client:
        result = client.post("/api/coach/analyze", json={"fen": chess.STARTING_FEN})
        assert result.status_code == 502
        app.state.db.save_coach_feedback.assert_not_called()
