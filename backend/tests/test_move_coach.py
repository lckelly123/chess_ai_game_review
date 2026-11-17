import asyncio
import json

import chess
import httpx2
import psycopg
import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from backend.chess_games import normalize_game
from backend.coach import Coach, CoachAnalysis, CoachPosition, CoachResponseError, CoachSettings, InvalidPositionError
from backend.coach.graph import build_coach_graph
from backend.coach.responses import MOVE_PROMPT_PATH
from backend.coach.stockfish import StockfishAnalysisError
from backend.database import Database
from backend.main import create_app
from backend.tests.test_app import raw_game
from backend.tests.test_coach import completed_response, teaching_output, teaching_text
from backend.tests.test_coach_graph import mock_client
from backend.tests.test_coach_routes import mock_coach_factory


FIRST = teaching_text()
SECOND = "### 3. Evaluate Your Move\n\n**Your Move**\nThis move follows the plan."


def move_response(**overrides):
    result = completed_response(id="resp_move", **overrides)
    result["output"][1]["content"][0]["text"] = SECOND
    return result


def evidence(review):
    candidate = {"uci": review.played_move_uci, "san": review.played_move_san,
                 "score": {"cp": 30, "mate": None, "bound": "exact"},
                 "pv_uci": [review.played_move_uci], "pv_san": [review.played_move_san], "depth": 18}
    return {"engine": "Stockfish test", "perspective": review.position.side_to_move,
            "top_moves": [candidate], "played_move": candidate, "played_move_in_top": True}


@pytest.mark.parametrize("model", ["gpt-6-astra", "gpt-6.1-terra"])
def test_second_responses_request_gets_exact_prior_output_board_move_and_evidence(model):
    requests = []
    board = chess.Board()
    board.push_uci("e2e4")
    fen = board.fen()

    def upstream(request):
        assert request.method == "POST"
        assert str(request.url) == "https://api.openai.com/v1/responses"
        body = json.loads(request.content)
        requests.append(body)
        return httpx2.Response(200, json=completed_response(request=request, model=model) if len(requests) == 1 else move_response(model=model))

    def engine(review):
        assert len(requests) == 1  # First analysis precedes engine-backed review.
        assert review.position.fen == fen
        assert review.played_move_uci == "e7e5"
        return evidence(review)

    async def run():
        async with mock_client(upstream) as client:
            return await Coach(client, CoachSettings(model=model), engine=engine).analyze(fen, played_move="e7e5")

    result = asyncio.run(run())
    assert len(requests) == 2
    assert "previous_analysis" not in json.dumps(requests[0])
    assert "Stockfish test" not in json.dumps(requests[0])
    assert "e7e5" not in json.dumps(requests[0])
    second = requests[1]
    assert second["input"][0]["content"] == MOVE_PROMPT_PATH.read_text(encoding="utf-8")
    payload = json.loads(second["input"][1]["content"].split("\n\n", 1)[1])
    assert payload["fen"] == fen
    assert payload["ascii_board"] == CoachPosition.from_fen(fen).ascii_board
    assert payload["previous_analysis"] == teaching_output(fen)
    assert "text" in requests[0] and "text" not in second
    assert payload["played_move"] == {"uci": "e7e5", "san": "e5"}
    assert payload["stockfish"] == result.stockfish
    assert requests[0]["model"] == second["model"] == model
    assert requests[0]["reasoning"] == second["reasoning"] == {"effort": "medium"}
    assert second["store"] is False and "previous_response_id" not in second
    assert result.text == teaching_text(fen) + "\n\n" + SECOND
    assert result.played_move == "e7e5"
    assert result.position_analysis["response_id"] == "resp_test"
    assert result.position_analysis["model"] == result.move_analysis["model"] == result.model == model
    assert result.move_analysis["response_id"] == result.response_id == "resp_move"
    assert result.usage["total_tokens"] == 320
    assert result.usage["output_tokens_details"]["reasoning_tokens"] == 40


def test_illegal_played_move_is_rejected_before_any_paid_request():
    def unexpected(*args):
        pytest.fail("Invalid move must not reach the engine or API")

    async def run():
        async with mock_client(unexpected) as client:
            with pytest.raises(InvalidPositionError):
                await Coach(client, engine=unexpected).analyze(chess.STARTING_FEN, played_move="e7e5")
    asyncio.run(run())


def test_checkpointed_runs_do_not_reuse_move_or_append_old_text():
    requests = []

    def upstream(request):
        body = json.loads(request.content)
        requests.append(body)
        is_second = body["input"][0]["content"] == MOVE_PROMPT_PATH.read_text(encoding="utf-8")
        return httpx2.Response(200, json=move_response() if is_second else completed_response(request=request))

    async def run():
        async with mock_client(upstream) as client:
            graph = Coach(client, engine=evidence).graph.builder.compile(checkpointer=InMemorySaver())
            config = {"configurable": {"thread_id": "review"}}
            first = await graph.ainvoke({"fen": chess.STARTING_FEN, "played_move": "e2e4"}, config)
            assert first["text"] == FIRST + "\n\n" + SECOND
            board = chess.Board()
            board.push_uci("e2e4")
            plain = await graph.ainvoke({"fen": board.fen()}, config)
            assert plain["move_uci"] is None and plain["stockfish"] is None and plain["move_analysis"] is None
            assert plain["text"] == teaching_text(board.fen())
            assert plain["position_analysis"]["structured"] == teaching_output(board.fen())
            rerun = await graph.ainvoke({"fen": chess.STARTING_FEN, "played_move": "d2d4"}, config)
            assert rerun["text"] == FIRST + "\n\n" + SECOND
            assert rerun["stockfish"]["played_move"]["uci"] == "d2d4"
            assert len(requests) == 5
    asyncio.run(run())


def test_new_input_after_failed_first_node_does_not_inherit_played_move():
    calls = []

    async def first(fen):
        calls.append(fen)
        if len(calls) == 1:
            raise CoachResponseError("first pass failed", "resp_failed")
        return CoachAnalysis(FIRST, "resp_test", "model", CoachPosition.from_fen(fen), None)

    async def run():
        graph = build_coach_graph(first).builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "failed-review"}}
        with pytest.raises(CoachResponseError):
            await graph.ainvoke({"fen": chess.STARTING_FEN, "played_move": "e2e4"}, config)
        board = chess.Board()
        board.push_uci("e2e4")
        result = await graph.ainvoke({"fen": board.fen()}, config)
        assert result["move_uci"] is None and result["text"] == FIRST
    asyncio.run(run())


def test_engine_failure_prevents_second_model_request():
    requests = []

    def upstream(request):
        requests.append(request)
        return httpx2.Response(200, json=completed_response())

    def failed_engine(review):
        raise StockfishAnalysisError("engine failed")

    async def run():
        async with mock_client(upstream) as client:
            with pytest.raises(StockfishAnalysisError):
                await Coach(client, engine=failed_engine).analyze(chess.STARTING_FEN, played_move="e2e4")
    asyncio.run(run())
    assert len(requests) == 1


@pytest.mark.parametrize("model", ["gpt-6-astra", "gpt-6.1-terra"])
def test_combined_review_persists_restores_and_keeps_other_moves_separate(test_db_url, model):
    db = Database(test_db_url)
    game = normalize_game(raw_game(), "alice")
    different = normalize_game(raw_game(2, pgn='[White "alice"]\n[Black "bob"]\n[Result "1-0"]\n\n1. d4 d5 1-0'), "alice")
    db.save_import("alice", [game, different], 1)
    calls = []

    def upstream(request):
        calls.append(json.loads(request.content))
        assert calls[-1]["model"] == model
        return httpx2.Response(200, json=completed_response(model=model) if len(calls) % 2 else move_response(model=model))

    factory = mock_coach_factory(upstream, engine=evidence)
    with TestClient(create_app(test_db_url, coach_factory=factory)) as client:
        result = client.post('/api/coach/analyze', json={"game_id": game["id"], "ply": 0, "model": model})
        assert result.status_code == 200
        saved = result.json()
        assert saved["text"] == FIRST + "\n\n" + SECOND
        assert saved["played_move"] == "e2e4"
        assert saved["model"] == model
        assert saved["teaching"] == teaching_output()
        assert saved["candidate_san"] == {"g1h3": "Nh3"}
        assert saved["stockfish"]["perspective"] == "White"
        assert saved["stockfish"]["played_move"]["score"] == {"cp": 30, "mate": None, "bound": "exact"}
        assert saved["stockfish"]["played_move"]["depth"] == 18
        assert client.get('/api/coach/feedback', params={"fen": chess.STARTING_FEN}).json() is None
        assert client.get(f'/api/games/{different["id"]}').json()["coach_responses"] == {}
    with TestClient(create_app(test_db_url, coach_factory=factory)) as restarted:
        assert restarted.get(f'/api/games/{game["id"]}').json()["coach_responses"]["0"] == saved
        assert restarted.get('/api/coach/feedback', params={"fen": chess.STARTING_FEN, "played_move": "e2e4"}).json() == saved
    assert len(calls) == 2
    with db.connection() as conn:
        row = conn.execute("SELECT position_analysis, move_analysis, stockfish, usage FROM coach_feedback").fetchone()
        assert row["position_analysis"]["text"] == FIRST
        assert row["position_analysis"]["structured"] == teaching_output()
        assert row["move_analysis"]["text"] == SECOND
        assert row["position_analysis"]["model"] == row["move_analysis"]["model"] == model
        assert row["stockfish"]["played_move"]["uci"] == "e2e4"
        assert row["usage"]["total_tokens"] == 320


@pytest.mark.parametrize("failure", ["incomplete", "refusal", "engine"])
def test_failed_second_pass_preserves_previous_combined_feedback(test_db_url, failure):
    db = Database(test_db_url)
    game = normalize_game(raw_game(), "alice")
    db.save_import("alice", [game], 1)
    previous = db.save_coach_feedback(CoachAnalysis("Earlier complete review", "old", "model",
                                     CoachPosition.from_fen(chess.STARTING_FEN), None, played_move="e2e4"))
    calls = []

    def upstream(request):
        calls.append(request)
        if len(calls) == 1:
            result = completed_response()
        elif failure == "incomplete":
            result = move_response(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
        else:
            result = move_response()
            result["output"][1]["content"] = [{"type": "refusal", "refusal": "No."}]
        return httpx2.Response(200, json=result)

    def engine(review):
        if failure == "engine":
            raise StockfishAnalysisError("private engine details")
        return evidence(review)

    with TestClient(create_app(test_db_url, coach_factory=mock_coach_factory(upstream, engine=engine))) as client:
        response = client.post('/api/coach/analyze', json={"game_id": game["id"], "ply": 0})
        assert response.status_code == 502
        assert "private" not in response.text
    assert db.coach_feedback_for_reviews([(chess.STARTING_FEN, "e2e4")])[(chess.STARTING_FEN, "e2e4")] == previous
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM coach_feedback").fetchone()["n"] == 1


def test_final_position_runs_only_first_pass_and_invalid_game_context_never_runs(test_db_url):
    db = Database(test_db_url)
    game = normalize_game(raw_game(), "alice")
    db.save_import("alice", [game], 1)
    calls = []

    def upstream(request):
        calls.append(request)
        return httpx2.Response(200, json=completed_response(request=request))

    def no_engine(review):
        pytest.fail("A final recorded position must not run Stockfish")

    with TestClient(create_app(test_db_url, coach_factory=mock_coach_factory(upstream, engine=no_engine))) as client:
        result = client.post('/api/coach/analyze', json={"game_id": game["id"], "ply": game["ply_count"]})
        assert result.status_code == 200
        assert result.json()["text"] == teaching_text(result.json()["fen"]) and result.json()["played_move"] is None
        for payload, code in [
            ({"game_id": "missing", "ply": 0}, 404),
            ({"game_id": game["id"], "ply": 999}, 422),
            ({"game_id": game["id"]}, 422),
            ({"game_id": game["id"], "ply": 0, "fen": chess.STARTING_FEN}, 422),
        ]:
            assert client.post('/api/coach/analyze', json=payload).status_code == code
    assert len(calls) == 1


def test_upgrade_preserves_old_rows_and_is_idempotent(test_db_url):
    with psycopg.connect(test_db_url) as conn:
        conn.execute("""CREATE TABLE coach_feedback (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, fen VARCHAR(256) NOT NULL,
            text TEXT NOT NULL, model TEXT NOT NULL, response_id TEXT NOT NULL,
            usage JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp())""")
        conn.execute("INSERT INTO coach_feedback(fen,text,model,response_id) VALUES (%s,'Old answer','model','old')", (chess.STARTING_FEN,))
    Database(test_db_url)
    db = Database(test_db_url)
    assert db.coach_feedback_for_positions([chess.STARTING_FEN])[chess.STARTING_FEN]["text"] == "Old answer"
    assert db.coach_feedback_for_reviews([(chess.STARTING_FEN, "e2e4")]) == {}
