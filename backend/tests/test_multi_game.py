import asyncio
import importlib
import json
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from openai import AsyncOpenAI
from pydantic import ValidationError

from backend.coach.responses import CoachResponseError
from backend.database import Database
from backend.lessons import lesson_analytics, multi_game_input
from backend.multi_game.graph import analyze_with_client, build_multi_game_graph, build_request, graph
from backend.multi_game.output import MultiGameReport
from backend.multi_game.service import MultiGameService, create_multi_game_router
from backend.tests.test_coach import completed_response
from backend.tests.test_lessons import MemoryDatabase as LessonDatabase, saved_move


def report():
    return {"profile_summary": "A preliminary pattern in the saved mistakes is passive defense.",
            "decision_patterns": [{"id": "pattern_1", "title": "Passive responses to pressure",
                "description": "Retreats concede activity when active alternatives exist.",
                "consequence": "The opponent keeps the initiative.",
                "thinking_adjustment": "Compare a retreat with an active defensive move.", "confidence": "medium"}],
            "foundation_priorities": [{"foundation": "defending", "priority": 1,
                "reason": "Active defense addresses the recurring retreats.", "related_pattern_ids": ["pattern_1"],
                "practice_focus": "Compare retreats and counterplay in the saved positions."}]}


def result():
    return {"report": report(), "response_id": "resp_multi", "model": "gpt-6-astra", "usage": None}


def test_input_matches_lessons_and_contains_exact_move_context_without_mutation():
    db = LessonDatabase()
    db.records.append({**deepcopy(db.records[0]), "id": "game-two"})
    first = next(iter(db.feedback.values()))
    first["teaching"].update(positional_thesis="Position explanation.", candidate_moves=[
        {"uci": "b1c3", "reason": "Develop the knight.", "highlight_squares": ["b1", "c3"]}])
    first["teaching"]["move_evaluation"]["explanation"] = "Move explanation."
    before = deepcopy((db.records, db.feedback))
    payload = multi_game_input(db, " ALICE ")
    assert payload["summary"] == lesson_analytics(db, "alice")
    assert [group["category"] for group in payload["mistakes_by_category"]] == [
        "tactical_miss", "tactical_allowed", "positional", "unclassified"]
    moves = [move for group in payload["mistakes_by_category"] for move in group["mistakes"]]
    assert len(moves) == payload["summary"]["errors"]["total"] == 6
    knight = next(move for move in moves if move["ply"] == 2)
    assert knight["opponent_previous_move"] == {"san": "e5", "uci": "e7e5"}
    assert knight["fen"] == db.records[0]["moves"]["2"]["fen"]
    assert "a b c d e f g h" in knight["ascii_board"]
    assert knight["move_number"] == 2 and knight["played_move"]["uci"] == "g1f3"
    assert knight["evaluation_perspective"] == "White" and knight["centipawn_loss"] == 70
    assert knight["previous_analysis"]["position_explanation"] == "Position explanation."
    assert knight["previous_analysis"]["played_move_explanation"] == "Move explanation."
    assert knight["previous_analysis"]["recommended_moves"] == [{"uci": "b1c3", "explanation": "Develop the knight."}]
    assert (db.records, db.feedback) == before


def test_input_keeps_unclassified_first_moves_mates_and_black_perspective():
    db = LessonDatabase()
    saved = saved_move(0, None)
    saved["stockfish"]["played_move"]["score"]["mate"] = -2
    saved["stockfish"]["played_move"]["pv_uci"] = ["e2e4", "e7e5"]
    db.records[0]["moves"] = {"0": saved, "1": saved_move(1, -200)}
    white = multi_game_input(db, "alice")["mistakes_by_category"][-1]["mistakes"]
    assert len(white) == 1
    assert white[0]["opponent_previous_move"] is None
    assert white[0]["centipawn_loss"] is None and white[0]["winning_chances_loss_pp"] is None
    assert white[0]["played_move"]["score"]["mate"] == -2
    assert white[0]["played_move"]["pv_uci"] == ["e2e4", "e7e5"]
    black = multi_game_input(db, "bob")["mistakes_by_category"][-1]["mistakes"][0]
    assert black["evaluation_perspective"] == "Black"
    assert black["opponent_previous_move"] == {"san": "e4", "uci": "e2e4"}


def test_output_contract_accepts_no_patterns_but_rejects_invalid_references_and_move_ids():
    assert MultiGameReport.model_validate({"profile_summary": "Insufficient evidence.", "decision_patterns": [], "foundation_priorities": []})
    invalid = []
    for field, value in [("related_pattern_ids", ["missing"]), ("priority", 2)]:
        sample = report()
        sample["foundation_priorities"][0][field] = value
        invalid.append(sample)
    sample = report()
    sample["decision_patterns"][0]["supporting_move_ids"] = ["made-up"]
    invalid.append(sample)
    sample = report()
    sample["decision_patterns"].append(sample["decision_patterns"][0])
    invalid.append(sample)
    sample = report()
    sample["profile_summary"] = "   "
    invalid.append(sample)
    for sample in invalid:
        with pytest.raises(ValidationError):
            MultiGameReport.model_validate(sample)


def test_separate_studio_graph_and_exact_astra_xhigh_request():
    config = json.loads((Path(__file__).resolve().parents[2] / "langgraph.json").read_text())
    module, name = config["graphs"]["multi_game_coach"].split(":")
    assert getattr(importlib.import_module(module), name) is graph
    assert {(edge.source, edge.target) for edge in graph.get_graph().edges} == {
        ("__start__", "analyze_patterns"), ("analyze_patterns", "__end__")}
    request = build_request(multi_game_input(LessonDatabase(), "alice"))
    assert request["model"] == "gpt-6-astra" and request["reasoning"] == {"effort": "xhigh"}
    assert request["store"] is False and request["truncation"] == "disabled"
    schema = request["text"]["format"]["schema"]
    assert request["text"]["format"]["strict"] is True
    assert set(schema["properties"]) == {"profile_summary", "decision_patterns", "foundation_priorities"}
    assert "supporting_move_ids" not in json.dumps(schema)


@pytest.mark.parametrize("failure", [None, "incomplete", "invalid", "refusal", "rate_limit"])
def test_real_sdk_adapter_makes_one_call_and_rejects_unusable_answers(failure):
    calls = []
    def upstream(request):
        calls.append(json.loads(request.content))
        if failure == "rate_limit":
            return httpx2.Response(429, json={"error": {"message": "Limited", "type": "rate_limit_error"}})
        response = completed_response()
        response["output"][-1]["content"][0]["text"] = json.dumps(report()) if failure != "invalid" else "{}"
        if failure == "incomplete":
            response.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
        if failure == "refusal":
            response["output"][-1]["content"] = [{"type": "refusal", "refusal": "Declined"}]
        return httpx2.Response(200, json=response)

    async def run():
        async with AsyncOpenAI(api_key="test-key", max_retries=0,
                               http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(upstream))) as client:
            workflow = build_multi_game_graph(lambda payload: analyze_with_client(client, payload))
            if failure:
                with pytest.raises(Exception):
                    await workflow.ainvoke(multi_game_input(LessonDatabase(), "alice"))
            else:
                response = await workflow.ainvoke(multi_game_input(LessonDatabase(), "alice"))
                assert response["report"] == report()
                assert response["usage"]["total_tokens"] == 160
    asyncio.run(run())
    assert len(calls) == 1
    assert calls[0]["reasoning"] == {"effort": "xhigh"}


def test_reused_graph_thread_does_not_send_previous_report():
    seen = []
    async def analyze(payload):
        seen.append(payload)
        return result()
    async def run():
        workflow = build_multi_game_graph(analyze).builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "multi-game"}}
        await workflow.ainvoke(multi_game_input(LessonDatabase(), "alice"), config=config)
        db = LessonDatabase()
        db.records[0]["id"] = "different-game"
        await workflow.ainvoke(multi_game_input(db, "alice"), config=config)
    asyncio.run(run())
    assert set(seen[1]) == {"summary", "mistakes_by_category"}
    assert "game-one" not in json.dumps(seen[1]) and "profile_summary" not in json.dumps(seen[1])


class MemoryDatabase(LessonDatabase):
    def __init__(self):
        super().__init__()
        self.runs = {}

    def multi_game_analyses(self, username):
        return [deepcopy(row) for row in reversed(list(self.runs.values())) if row["username"] == username]

    def begin_multi_game_analysis(self, run_id, username, payload, model, effort):
        row = {"id": run_id, "username": username, "status": "queued", "summary": deepcopy(payload["summary"]),
               "report": None, "model": model, "reasoning_effort": effort, "response_id": None, "error": None,
               "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
        self.runs[run_id] = row
        return deepcopy(row)

    def set_multi_game_status(self, run_id, status, error=None):
        if self.runs[run_id]["status"] in {"queued", "running"}:
            self.runs[run_id].update(status=status, error=error)

    def complete_multi_game_analysis(self, run_id, value):
        self.runs[run_id].update(value, status="completed", error=None)


def test_background_run_overlap_history_failure_and_read_only_gets():
    db, tasks = MemoryDatabase(), set()
    release = threading.Event()
    calls = []
    async def analyze(payload):
        calls.append(payload)
        while not release.is_set():
            await asyncio.sleep(.01)
        if len(calls) == 2:
            raise CoachResponseError("Bad answer", "resp_bad")
        return result()
    app = FastAPI()
    app.state.multi_game = MultiGameService(db, tasks, analyze)
    app.include_router(create_multi_game_router())

    def finish(client):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            rows = client.get('/api/lessons/multi-game?username=alice').json()
            if rows[0]['status'] not in {'queued', 'running'}:
                return rows
            time.sleep(.01)
        pytest.fail("Background analysis did not complete")

    with TestClient(app) as client:
        assert client.get('/api/lessons/multi-game?username=ALICE').json() == []
        assert calls == []
        assert client.post('/api/lessons/multi-game', json={"username": " ALICE "}).status_code == 202
        assert client.post('/api/lessons/multi-game', json={"username": "alice"}).status_code == 409
        release.set()
        rows = finish(client)
        assert rows[0]['report'] == report() and rows[0]['status'] == 'completed'
        assert client.get('/api/lessons/multi-game?username=bob').json() == []
        assert client.post('/api/lessons/multi-game', json={"username": "alice"}).status_code == 202
        rows = finish(client)
        assert rows[0]['status'] == 'failed' and rows[0]['report'] is None
        assert rows[1]['report'] == report()  # Failed rerun preserves previous answer.
        assert len(calls) == 2
        db.records.clear()
        assert client.post('/api/lessons/multi-game', json={"username": "alice"}).status_code == 422
        assert client.post('/api/lessons/multi-game', json={"username": "alice", "model": "other"}).status_code == 422
        assert client.get('/api/lessons/multi-game?username=bad%20name').status_code == 422
        assert len(calls) == 2


def test_cancelled_and_orphaned_runs_are_recoverable():
    async def run():
        db, tasks = MemoryDatabase(), set()
        entered = asyncio.Event()
        async def analyze(payload):
            entered.set()
            await asyncio.Future()
        service = MultiGameService(db, tasks, analyze)
        row = await service.start("alice")
        await entered.wait()
        task = next(iter(tasks))
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert (await service.saved("alice"))[0]["status"] == "interrupted"
        db.runs[row["id"]]["status"] = "running"  # Simulate a failed status write.
        assert (await service.saved("alice"))[0]["status"] == "interrupted"
    asyncio.run(run())


def test_postgres_history_snapshot_and_restart(test_db_url):
    import psycopg
    db = Database(test_db_url)
    payload = multi_game_input(LessonDatabase(), "alice")
    first = db.begin_multi_game_analysis("run-one", "alice", payload, "gpt-6-astra", "xhigh")
    assert first["summary"] == payload["summary"] and "input_snapshot" not in first
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.begin_multi_game_analysis("duplicate", "alice", payload, "gpt-6-astra", "xhigh")
    db.complete_multi_game_analysis("run-one", result())
    db.begin_multi_game_analysis("run-two", "alice", payload, "gpt-6-astra", "xhigh")
    restarted = Database(test_db_url)
    restarted.interrupt_multi_game_analyses()
    history = restarted.multi_game_analyses("alice")
    assert [row["status"] for row in history] == ["interrupted", "completed"]
    assert history[1]["report"] == report()
    assert restarted.multi_game_analyses("bob") == []
    with restarted.connection() as connection:
        snapshot = connection.execute("SELECT input_snapshot FROM multi_game_analysis WHERE id='run-one'").fetchone()
    assert snapshot["input_snapshot"] == payload
