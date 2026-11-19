import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import threading
import time

import chess
import pytest
from fastapi.testclient import TestClient

from backend.chess_games import normalize_game, replay
from backend.coach.move_review import MoveReview
from backend.coach.player_move_quality import assess_player_move
from backend.coach.stockfish import StockfishAnalysisError, StockfishSettings, StockfishTimeoutError
from backend.database import Database
from backend.game_analysis import (
    GameAnalysisService, analysis_result, analysis_summary, analyze_game_move,
    pgn_fingerprint, quality_counts,
)
from backend.main import create_app
from backend.tests.position_fixtures import position_evidence
from backend.tests.test_app import raw_game


def evidence(review):
    position = position_evidence(review.position.fen)
    return {"fen": review.position.fen, "engine": "Stockfish fixture", "perspective": review.position.side_to_move,
            "top_moves": position["top_moves"], "played_move": {
                "uci": review.played_move_uci, "san": review.played_move_san, "rank": None, "depth": 12,
                "score": {"cp": -200, "mate": None, "bound": "exact"},
            }, "move_quality": {"status": "good"}}  # The service must apply the shared grader.


class MemoryDatabase:
    """Exercise the real job/router lifecycle without depending on PostgreSQL."""
    def __init__(self):
        self.record = normalize_game(raw_game(), "alice")
        self.rows = {}

    def game(self, game_id):
        return deepcopy(self.record) if game_id == self.record["id"] else None

    def game_analysis(self, game_id, color, fingerprint):
        row = self.rows.get((game_id, color))
        return deepcopy(row) if row and row["pgn_hash"] == fingerprint else None

    def begin_game_analysis(self, game_id, color, fingerprint, total):
        key = (game_id, color)
        row = self.game_analysis(game_id, color, fingerprint)
        if row is None:
            row = {"game_id": game_id, "player_color": color, "pgn_hash": fingerprint, "status": "queued",
                   "total": total, "completed": 0, "counts": {}, "moves": {}, "error": None,
                   "updated_at": datetime.now(timezone.utc)}
        if row["status"] != "completed":
            row.update(status="queued", error=None)
        self.rows[key] = row
        return deepcopy(row)

    def save_game_analysis_move(self, game_id, color, fingerprint, ply, result):
        row = self.rows[(game_id, color)]
        if row["pgn_hash"] != fingerprint:
            return False
        row["moves"][str(ply)] = deepcopy(result)
        row.update(completed=len(row["moves"]), counts=quality_counts(row["moves"]))
        return True

    def set_game_analysis_status(self, game_id, color, fingerprint, status, error):
        row = self.rows[(game_id, color)]
        if row["pgn_hash"] == fingerprint:
            row.update(status=status, error=error)

    def interrupt_game_analyses(self):
        for row in self.rows.values():
            if row["status"] in {"queued", "running"}:
                row.update(status="interrupted", error="Analysis paused. Resume to finish.")

    def game_analyses(self, game_id, pgn):
        return {color: analysis_result(row) for (key, color), row in self.rows.items()
                if key == game_id and row["pgn_hash"] == pgn_fingerprint(pgn)}

    def coach_feedback_for_reviews(self, reviews):
        return {}

    def games(self, username):
        color = "white" if username == "alice" else "black"
        row = self.game_analysis(self.record["id"], color, pgn_fingerprint(self.record["pgn"]))
        return [{k: v for k, v in self.record.items() if k != "pgn"} | {"analysis": analysis_summary(row)}]


async def finish(service):
    await asyncio.gather(*list(service.tasks))
    await asyncio.sleep(0)  # Run completion callbacks before another start.


@pytest.mark.parametrize("username,expected", [("ALICE", [0, 2, 4, 6]), ("bob", [1, 3, 5])])
def test_only_selected_players_pre_move_positions_are_analyzed_and_saved(username, expected):
    db = MemoryDatabase()
    calls = []
    def engine(review):
        calls.append(review)
        return evidence(review)
    async def run():
        service = GameAnalysisService(db, set(), engine)
        job = await service.start(db.record["id"], username)
        assert job["total"] == len(expected)
        await finish(service)
        saved = await service.start(db.record["id"], username)
        assert saved["status"] == "completed"
        assert set(saved["moves"]) == {str(ply) for ply in expected}
        assert saved["completed"] == len(expected) and saved["counts"] == {"blunder": len(expected)}
        detail = replay(db.record["pgn"])
        for ply, review in zip(expected, calls):
            result = saved["moves"][str(ply)]
            assert review.position.fen == detail["positions"][ply]["fen"]
            assert result["played_move"] == detail["moves"][ply]["uci"]
            assert result["stockfish"]["move_quality"] == assess_player_move(
                result["stockfish"]["top_moves"][0], result["stockfish"]["played_move"])
        assert not service.tasks and len(calls) == len(expected)  # Completed work is reused.
    asyncio.run(run())


def test_failure_keeps_progress_and_resume_skips_saved_moves():
    db = MemoryDatabase()
    calls = []
    def engine(review):
        calls.append(review.played_move_uci)
        if len(calls) == 2:
            raise StockfishTimeoutError("private engine diagnostic")
        return evidence(review)
    async def run():
        service = GameAnalysisService(db, set(), engine)
        await service.start(db.record["id"], "alice")
        await finish(service)
        row = db.rows[(db.record["id"], "white")]
        assert row["status"] == "failed" and row["completed"] == 1
        assert "private" not in row["error"]
        await service.start(db.record["id"], "alice")
        await finish(service)
        assert row["moves"]["0"]["played_move"] == "e2e4"
        assert db.rows[(db.record["id"], "white")]["status"] == "completed"
        assert calls == ["e2e4", "g1f3", "g1f3", "f1c4", "e1g1"]
    asyncio.run(run())


def test_overlapping_starts_share_one_job_and_games_queue_without_parallel_engines():
    db = MemoryDatabase()
    entered, release = threading.Event(), threading.Event()
    calls = []
    def engine(review):
        calls.append(review.position.side_to_move)
        entered.set()
        assert release.wait(5)
        return evidence(review)
    async def run():
        service = GameAnalysisService(db, set(), engine)
        first, duplicate = await asyncio.gather(service.start(db.record["id"], "alice"), service.start(db.record["id"], "alice"))
        assert first["total"] == duplicate["total"] == 4 and len(service.active) == 1
        assert await asyncio.to_thread(entered.wait, 5)
        black = await service.start(db.record["id"], "bob")
        assert black["status"] == "queued"
        assert calls == ["White"]
        release.set()
        await finish(service)
        assert calls == ["White"] * 4 + ["Black"] * 3
    try:
        asyncio.run(run())
    finally:
        release.set()


def test_custom_black_start_uses_move_colors_not_even_odd_indices():
    db = MemoryDatabase()
    db.record["pgn"] = '[SetUp "1"]\n[FEN "8/7k/8/8/8/8/P7/K7 b - - 0 23"]\n\n23... Kg6 24. a4 Kf5 25. a5 *'
    async def run():
        service = GameAnalysisService(db, set(), evidence)
        await service.start(db.record["id"], "bob")
        await finish(service)
        row = db.rows[(db.record["id"], "black")]
        assert set(row["moves"]) == {"0", "2"} and row["total"] == 2
    asyncio.run(run())


def test_wrong_position_evidence_is_rejected_before_saving():
    db = MemoryDatabase()
    def wrong(review):
        return {**evidence(review), "perspective": "Black"}
    async def run():
        service = GameAnalysisService(db, set(), wrong)
        await service.start(db.record["id"], "alice")
        await finish(service)
        row = db.rows[(db.record["id"], "white")]
        assert row["status"] == "failed" and row["moves"] == {} and row["completed"] == 0
    asyncio.run(run())


def test_cancelled_worker_keeps_progress_and_can_resume():
    db = MemoryDatabase()
    entered, release = threading.Event(), threading.Event()
    def engine(review):
        if review.played_move_uci == "g1f3":
            entered.set()
            assert release.wait(5)
        return evidence(review)
    async def run():
        service = GameAnalysisService(db, set(), engine)
        await service.start(db.record["id"], "alice")
        assert await asyncio.to_thread(entered.wait, 5)
        task = service.active[(db.record["id"], "white")]
        task.cancel()
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)
        row = db.rows[(db.record["id"], "white")]
        assert row["status"] == "interrupted" and row["completed"] == 1
        await service.start(db.record["id"], "alice")
        await finish(service)
        assert db.rows[(db.record["id"], "white")]["completed"] == 4
    try:
        asyncio.run(run())
    finally:
        release.set()


def test_polling_recovers_orphaned_status_after_database_outage():
    db = MemoryDatabase()
    game_id = db.record["id"]
    fingerprint = pgn_fingerprint(db.record["pgn"])
    db.begin_game_analysis(game_id, "white", fingerprint, 4)
    db.set_game_analysis_status(game_id, "white", fingerprint, "running", None)
    async def run():
        service = GameAnalysisService(db, set(), evidence)
        job = await service.saved(game_id, "alice")
        assert job["status"] == "interrupted" and not service.tasks
    asyncio.run(run())


def test_changed_pgn_discards_stale_analysis_and_reanalyzes_new_game():
    db = MemoryDatabase()
    calls = []
    def engine(review):
        calls.append(review.played_move_uci)
        return evidence(review)
    async def run():
        service = GameAnalysisService(db, set(), engine)
        await service.start(db.record["id"], "alice")
        await finish(service)
        db.record["pgn"] = '1. d4 d5 2. c4 *'
        assert db.game_analyses(db.record["id"], db.record["pgn"]) == {}
        await service.start(db.record["id"], "alice")
        await finish(service)
        row = db.rows[(db.record["id"], "white")]
        assert row["completed"] == 2 and set(row["moves"]) == {"0", "2"}
        assert row["moves"]["0"]["played_move"] == "d2d4" and len(calls) == 6
    asyncio.run(run())


def wait_completed(client, game_id, username="alice"):
    for _ in range(200):
        response = client.get(f'/api/games/{game_id}/analysis', params={"username": username})
        assert response.status_code == 200
        job = response.json()
        if job and job["status"] not in {"queued", "running"}:
            assert job["status"] == "completed", job
            return job
        time.sleep(.01)
    pytest.fail("Engine job did not finish")


def test_http_job_survives_navigation_and_restart_without_model_calls(monkeypatch):
    db = MemoryDatabase()
    monkeypatch.setattr('backend.main.Database', lambda _: db)
    calls = []
    def engine(review):
        calls.append(review.played_move_uci)
        return evidence(review)
    def no_coach(*args, **kwargs):
        pytest.fail("Game analysis must not call the coach")
    game_id = db.record["id"]
    with TestClient(create_app("unused", game_engine=engine, coach_factory=no_coach)) as client:
        assert client.get(f'/api/games/{game_id}/analysis?username=alice').json() is None
        assert client.post('/api/games/missing/analysis', json={"username": "alice"}).status_code == 404
        assert client.post(f'/api/games/{game_id}/analysis', json={"username": "outsider"}).status_code == 422
        assert client.post(f'/api/games/{game_id}/analysis', json={"username": "alice", "fen": "untrusted"}).status_code == 422
        assert calls == []
        assert client.post(f'/api/games/{game_id}/analysis', json={"username": " ALICE "}).status_code == 202
        saved = wait_completed(client, game_id)
        assert client.get(f'/api/games/{game_id}').json()["engine_analyses"]["white"] == saved
        summary = client.get('/api/games?username=alice').json()[0]["analysis"]
        assert summary["completed"] == 4 and "moves" not in summary
    with TestClient(create_app("unused", game_engine=engine, coach_factory=no_coach)) as restarted:
        assert restarted.get(f'/api/games/{game_id}/analysis?username=alice').json() == saved
        assert restarted.post(f'/api/games/{game_id}/analysis', json={"username": "alice"}).json() == saved
        assert len(calls) == 4


def test_interrupted_work_resumes_after_restart(monkeypatch):
    db = MemoryDatabase()
    game_id = db.record["id"]
    fingerprint = pgn_fingerprint(db.record["pgn"])
    db.begin_game_analysis(game_id, 'white', fingerprint, 4)
    db.set_game_analysis_status(game_id, 'white', fingerprint, 'running', None)
    monkeypatch.setattr('backend.main.Database', lambda _: db)
    with TestClient(create_app("unused", game_engine=evidence)) as client:
        assert client.get(f'/api/games/{game_id}/analysis?username=alice').json()["status"] == "interrupted"
        client.post(f'/api/games/{game_id}/analysis', json={"username": "alice"})
        assert wait_completed(client, game_id)["completed"] == 4


def test_real_stockfish_game_move_reuses_shared_search_and_grading(monkeypatch):
    # Low-cost smoke at a fixed small depth; no OpenAI or database needed.
    settings = StockfishSettings(depth=6, time_limit=1, threads=1, hash_mb=16)
    try:
        settings.executable()
    except Exception as exc:
        pytest.skip(str(exc))
    monkeypatch.setattr(StockfishSettings, "from_env", lambda: settings)
    for ply in [0, 1]:
        review = MoveReview.from_game('1. f3 e5 2. g4 *', ply)
        result = analyze_game_move(review)
        assert result["fen"] == review.position.fen and result["perspective"] == review.position.side_to_move
        assert len(result["top_moves"]) == 5 and result["played_move"]["uci"] == review.played_move_uci
        assert result["move_quality"] == assess_player_move(result["top_moves"][0], result["played_move"])


def test_postgres_progress_persists_and_completed_game_restores(test_db_url):
    db = Database(test_db_url)
    game = normalize_game(raw_game(), "alice")
    db.save_import("alice", [game], 1)
    calls = []
    def engine(review):
        calls.append(review.played_move_uci)
        return evidence(review)
    with TestClient(create_app(test_db_url, game_engine=engine)) as client:
        client.post(f'/api/games/{game["id"]}/analysis', json={"username": "alice"})
        saved = wait_completed(client, game["id"])
        assert saved["counts"] == {"blunder": 4}
    with TestClient(create_app(test_db_url, game_engine=engine)) as client:
        assert client.get(f'/api/games/{game["id"]}').json()["engine_analyses"]["white"] == saved
        assert client.get('/api/games?username=alice').json()[0]["analysis"]["counts"] == {"blunder": 4}
        client.post(f'/api/games/{game["id"]}/analysis', json={"username": "alice"})
        assert len(calls) == 4


def test_postgres_resume_keeps_saved_moves_and_separates_colors(test_db_url):
    db = Database(test_db_url)
    game = normalize_game(raw_game(), "alice")
    db.save_import("alice", [game], 1)
    fingerprint = pgn_fingerprint(game["pgn"])
    db.begin_game_analysis(game["id"], "white", fingerprint, 4)
    review = MoveReview.from_game(game["pgn"], 0)
    first = {"fen": review.position.fen, "played_move": review.played_move_uci, "stockfish": evidence(review)}
    assert db.save_game_analysis_move(game["id"], "white", fingerprint, 0, first)
    assert not db.save_game_analysis_move(game["id"], "white", "stale", 2, first)
    with TestClient(create_app(test_db_url, game_engine=evidence)) as client:
        partial = client.get(f'/api/games/{game["id"]}/analysis?username=alice').json()
        assert partial["status"] == "interrupted" and partial["completed"] == 1
        client.post(f'/api/games/{game["id"]}/analysis', json={"username": "alice"})
        assert wait_completed(client, game["id"])["moves"]["0"] == first
        assert client.get(f'/api/games/{game["id"]}/analysis?username=bob').json() is None
