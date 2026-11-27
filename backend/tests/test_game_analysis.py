import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
import threading
import time
from uuid import uuid4

import chess
import pytest
from fastapi.testclient import TestClient

from backend.chess_games import normalize_game, replay
from backend.coach.classification import CLASSIFICATION_VERSION
from backend.coach.context import COACH_CONTRACT_VERSION, context_key
from backend.tests.test_coach import teaching_output
from backend.coach.move_review import MoveReview
from backend.coach.responses import CoachAnalysis, CoachResponseError
from backend.coach.position import CoachPosition
from backend.coach.player_move_quality import assess_player_move
from backend.coach.stockfish import StockfishAnalysisError, StockfishSettings, StockfishTimeoutError
from backend.database import Database
from backend.game_analysis import (
    GameAnalysisService, analysis_result, analysis_summary, analyze_game_move,
    pgn_fingerprint, quality_counts,
)
from backend.game_statistics import STATISTICS_VERSION, position_evaluation, terminal_evaluation
from backend.main import create_app as real_create_app
from backend.tests.position_fixtures import position_evidence
from backend.tests.test_app import raw_game


class FakeCoach:
    async def analyze(self, fen, *, played_move=None, previous_move=None):
        return CoachAnalysis(text="Review this decision.", response_id=str(uuid4()), model="gpt-6-astra",
                             position=CoachPosition.from_fen(fen), usage=None, played_move=played_move,
                             previous_move=previous_move,
                             position_analysis={"classification_version": CLASSIFICATION_VERSION, "coach_contract_version": COACH_CONTRACT_VERSION,
                                                "previous_move": previous_move, "structured": teaching_output(fen)})


@asynccontextmanager
async def fake_coach(settings, **kwargs):
    yield FakeCoach()


@pytest.fixture(autouse=True)
def mock_background_coach(monkeypatch):
    monkeypatch.setattr('backend.game_analysis.open_coach', fake_coach)
    def final(pgn):
        from backend.chess_games import parse_game
        board = parse_game(pgn).end().board()
        ply = len(replay(pgn)['moves'])
        return terminal_evaluation(board, ply) or position_evaluation(position_evidence(board.fen()), ply, board.fen())
    monkeypatch.setattr('backend.game_analysis.analyze_final_position', final)


def create_app(*args, **kwargs):
    kwargs.setdefault('coach_factory', fake_coach)
    return real_create_app(*args, **kwargs)


def evidence(review):
    position = position_evidence(review.position.fen, preferred=[m.uci() for m in chess.Board(review.position.fen).legal_moves if m.uci() != review.played_move_uci][:5])
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
        self.feedback = {}

    def health(self):
        pass

    def mark_engine_move(self, *args):
        return True

    def move_engine(self, game_id, ply):
        return None

    def game_reviews(self, game_id):
        return {}

    def game_replay(self, game_id):
        return replay(self.record["pgn"])

    def save_coach_feedback(self, analysis, *, game_id=None, expected_revision=0, decision_ply=None):
        saved = {"fen": analysis.position.fen, "played_move": analysis.played_move,
                 "text": analysis.text, "model": analysis.model, "response_id": analysis.response_id,
                 "created_at": datetime.now(timezone.utc), "stockfish": analysis.stockfish,
                 "classification_version": (analysis.position_analysis or {}).get("classification_version"),
                 "coach_contract_version": (analysis.position_analysis or {}).get("coach_contract_version"),
                 "teaching": (analysis.position_analysis or {}).get("structured")}
        self.feedback[(analysis.position.fen, analysis.played_move, context_key(analysis.previous_move))] = saved
        return saved

    def save_game_coach_progress(self, game_id, color, fingerprint, completed):
        row = self.rows[(game_id, color)]
        if row['pgn_hash'] != fingerprint:
            return False
        row['coach_completed'] = max(row.get('coach_completed', 0), completed)
        return True

    def game(self, game_id):
        return deepcopy(self.record) if game_id == self.record["id"] else None

    def game_analysis(self, game_id, color, fingerprint):
        row = self.rows.get((game_id, color))
        return deepcopy(row) if row and row["pgn_hash"] == fingerprint else None

    def begin_game_analysis(self, game_id, color, fingerprint, total, opponent_total=None):
        key = (game_id, color)
        row = self.game_analysis(game_id, color, fingerprint)
        if row is None:
            row = {"game_id": game_id, "player_color": color, "pgn_hash": fingerprint, "status": "queued",
                   "total": total, "completed": 0, "counts": {}, "moves": {}, "error": None,
                   "updated_at": datetime.now(timezone.utc), "coach_completed": 0, "coach_version": COACH_CONTRACT_VERSION,
                   "opponent_total": None, "opponent_moves": {}, "statistics": None}
        if row.get("coach_version") != COACH_CONTRACT_VERSION:
            row.update(coach_version=COACH_CONTRACT_VERSION, coach_completed=0)
        if (row["status"] != "completed" or row.get('coach_completed', 0) < sum(row['counts'].get(q, 0) for q in ('inaccuracy', 'mistake', 'blunder'))
                or (row.get('statistics') or {}).get('version') != STATISTICS_VERSION
                or (opponent_total is not None and (row.get('opponent_total') != opponent_total or len(row['opponent_moves']) != opponent_total))):
            row.update(status="queued", error=None)
        if opponent_total is not None:
            row['opponent_total'] = opponent_total
        self.rows[key] = row
        return deepcopy(row)

    def save_game_statistics(self, game_id, color, fingerprint, statistics):
        row = self.rows[(game_id, color)]
        if row['pgn_hash'] != fingerprint:
            return False
        row['statistics'] = deepcopy(statistics)
        return True

    def save_game_analysis_move(self, game_id, color, fingerprint, ply, result):
        row = self.rows[(game_id, color)]
        if row["pgn_hash"] != fingerprint:
            return False
        row["moves"][str(ply)] = deepcopy(result)
        row.update(completed=len(row["moves"]), counts=quality_counts(row["moves"]))
        return True

    def save_game_opponent_move(self, game_id, color, fingerprint, ply, result):
        row = self.rows[(game_id, color)]
        if row['pgn_hash'] != fingerprint:
            return False
        row['opponent_moves'][str(ply)] = deepcopy(result)
        return True

    def set_game_analysis_status(self, game_id, color, fingerprint, status, error):
        row = self.rows[(game_id, color)]
        if row["pgn_hash"] == fingerprint:
            row.update(status=status, error=error)

    def interrupt_game_analyses(self):
        for row in self.rows.values():
            if row["status"] in {"queued", "running"}:
                row.update(status="interrupted", error="Analysis paused. Resume to finish.")

    def interrupt_multi_game_analyses(self):
        pass  # This test double only exercises per-game analysis.

    def game_analyses(self, game_id, pgn):
        return {color: analysis_result(row) for (key, color), row in self.rows.items()
                if key == game_id and row["pgn_hash"] == pgn_fingerprint(pgn)}

    def coach_feedback_for_reviews(self, reviews, *, game_id=None):
        return {key: deepcopy(self.feedback[key]) for key in reviews if key in self.feedback}

    def games(self, username):
        color = "white" if username == "alice" else "black"
        row = self.game_analysis(self.record["id"], color, pgn_fingerprint(self.record["pgn"]))
        return [{k: v for k, v in self.record.items() if k != "pgn"} | {"analysis": analysis_summary(row)}]


async def finish(service):
    await asyncio.gather(*list(service.tasks))
    await asyncio.sleep(0)  # Run completion callbacks before another start.


@pytest.mark.parametrize("username,expected", [("ALICE", [0, 2, 4, 6]), ("bob", [1, 3, 5])])
def test_both_sides_are_saved_but_only_selected_player_is_counted_and_coached(username, expected):
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
        opponents = set(range(7)) - set(expected)
        assert set(saved['opponent_moves']) == {str(ply) for ply in opponents}
        assert saved['opponent_total'] == saved['opponent_completed'] == len(opponents)
        assert len(db.feedback) == len(expected)
        detail = replay(db.record["pgn"])
        for ply, review in zip(expected, calls):
            result = saved["moves"][str(ply)]
            assert review.position.fen == detail["positions"][ply]["fen"]
            assert result["played_move"] == detail["moves"][ply]["uci"]
            assert result["stockfish"]["move_quality"] == assess_player_move(
                result["stockfish"]["top_moves"][0], result["stockfish"]["played_move"])
        assert not service.tasks and len(calls) == 7  # Both sides' completed work is reused.
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
        assert calls == ["e2e4", "g1f3", "g1f3", "f1c4", "e1g1", "e7e5", "b8c6", "g8f6"]
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
        assert set(row['opponent_moves']) == {'1', '3'}
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


def test_polling_preserves_completion_when_worker_finishes_during_status_read():
    async def run():
        db = MemoryDatabase()
        game_id = db.record["id"]
        fingerprint = pgn_fingerprint(db.record["pgn"])
        db.begin_game_analysis(game_id, "white", fingerprint, 4)
        row = db.rows[(game_id, "white")]
        row["status"] = "running"
        stale = deepcopy(row)
        row["status"] = "completed"
        original = db.game_analysis
        reads = []

        def read(*args):
            reads.append(args)
            # The first snapshot was taken before the worker completed.
            return stale if len(reads) == 1 else original(*args)

        db.game_analysis = read
        service = GameAnalysisService(db, set())
        result = await service.saved(game_id, "alice")
        assert result["status"] == row["status"] == "completed"
        assert len(reads) == 2

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
        assert row["moves"]["0"]["played_move"] == "d2d4" and len(calls) == 10
        assert set(row['opponent_moves']) == {'1'}
        assert row['opponent_moves']['1']['played_move'] == 'd7d5'
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


def test_http_job_saves_coaching_and_reuses_it_after_navigation_and_restart(monkeypatch):
    db = MemoryDatabase()
    monkeypatch.setattr('backend.main.Database', lambda _: db)
    calls = []
    def engine(review):
        calls.append(review.played_move_uci)
        return evidence(review)
    coach_calls = []
    @asynccontextmanager
    async def factory(settings, **kwargs):
        coach_calls.append(settings.model)
        yield FakeCoach()
    game_id = db.record["id"]
    with TestClient(create_app("unused", game_engine=engine, coach_factory=factory)) as client:
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
        assert summary['coach_completed'] == summary['coach_total'] == 4
        assert set(client.get(f'/api/games/{game_id}').json()['coach_responses']) == {'0', '2', '4', '6'}
    with TestClient(create_app("unused", game_engine=engine, coach_factory=factory)) as restarted:
        assert restarted.get(f'/api/games/{game_id}/analysis?username=alice').json() == saved
        assert restarted.post(f'/api/games/{game_id}/analysis', json={"username": "alice"}).json() == saved
        assert len(calls) == 7
        assert coach_calls == ['gpt-6-astra'] * 4


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
        assert "tactic_classification" not in result


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
        assert all("tactic_classification" not in move["stockfish"]
                   for move in saved["moves"].values())
    with TestClient(create_app(test_db_url, game_engine=engine)) as client:
        assert client.get(f'/api/games/{game["id"]}').json()["engine_analyses"]["white"] == saved
        assert client.get('/api/games?username=alice').json()[0]["analysis"]["counts"] == {"blunder": 4}
        client.post(f'/api/games/{game["id"]}/analysis', json={"username": "alice"})
        assert len(calls) == 7


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
    assert not db.save_game_opponent_move(game['id'], 'white', 'stale', 1, first)
    with TestClient(create_app(test_db_url, game_engine=evidence)) as client:
        partial = client.get(f'/api/games/{game["id"]}/analysis?username=alice').json()
        assert partial["status"] == "interrupted" and partial["completed"] == 1
        client.post(f'/api/games/{game["id"]}/analysis', json={"username": "alice"})
        restored = wait_completed(client, game["id"])["moves"]["0"]
        assert restored["fen"] == first["fen"] and restored["played_move"] == first["played_move"]
        assert restored["stockfish"]["played_move"]["score"] == first["stockfish"]["played_move"]["score"]
        assert restored['position_evidence']['sharpness']['score'] is not None
        assert db.game_analysis(game['id'], 'white', fingerprint)['moves']['0']['stockfish']['top_moves'][0]['score'] == first['stockfish']['top_moves'][0]['score']
        assert client.get(f'/api/games/{game["id"]}/analysis?username=bob').json() is None


def test_completed_legacy_run_adds_opponents_without_repeating_player_engine_or_coach():
    db = MemoryDatabase()
    async def run():
        service = GameAnalysisService(db, set(), evidence)
        await service.start(db.record['id'], 'alice')
        await finish(service)
        row = db.rows[(db.record['id'], 'white')]
        player_evidence, coaching = deepcopy(row['moves']), deepcopy(db.feedback)
        row.update(opponent_total=None, opponent_moves={})  # Pre-upgrade completed run.
        calls = []
        def opponent_engine(review):
            assert review.position.side_to_move == 'Black'
            calls.append(review.played_move_uci)
            return evidence(review)
        service.analyzer = opponent_engine
        started = await service.start(db.record['id'], 'alice')
        assert started['status'] == 'queued' and started['opponent_total'] == 3
        await finish(service)
        saved = await service.saved(db.record['id'], 'alice')
        assert saved['status'] == 'completed' and saved['opponent_completed'] == 3
        assert db.rows[(db.record['id'], 'white')]['moves'] == player_evidence and db.feedback == coaching
        assert calls == ['e7e5', 'b8c6', 'g8f6']
    asyncio.run(run())


def test_opponent_failure_is_resumable_and_does_not_inflate_player_counts():
    db = MemoryDatabase()
    calls = []
    def engine(review):
        calls.append(review.played_move_uci)
        if len(calls) == 6:
            raise StockfishTimeoutError('private')
        return evidence(review)
    async def run():
        service = GameAnalysisService(db, set(), engine)
        await service.start(db.record['id'], 'alice')
        await finish(service)
        partial = await service.saved(db.record['id'], 'alice')
        assert partial['status'] == 'failed' and partial['opponent_completed'] == 1
        assert partial['completed'] == partial['total'] == 4 and partial['counts'] == {'blunder': 4}
        await service.start(db.record['id'], 'alice')
        await finish(service)
        saved = await service.saved(db.record['id'], 'alice')
        assert saved['status'] == 'completed' and saved['opponent_completed'] == 3
        assert saved['counts'] == {'blunder': 4} and len(db.feedback) == 4
        assert calls == ['e2e4', 'g1f3', 'f1c4', 'e1g1', 'e7e5', 'b8c6', 'b8c6', 'g8f6']
    asyncio.run(run())


def test_automatic_coach_selects_only_three_error_grades_and_reuses_exact_evidence():
    db = MemoryDatabase()
    db.record['pgn'] = '1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. d3 Nf6 5. O-O *'
    scores = {'e2e4': 100, 'g1f3': 30, 'f1c4': -30, 'd2d3': -100, 'e1g1': None}
    engine_calls, coach_calls = [], []
    def engine(review):
        engine_calls.append(review.played_move_uci)
        result = evidence(review)
        result['played_move']['score']['cp'] = scores.get(review.played_move_uci, -200)
        result['position_evidence'] = position_evidence(review.position.fen)
        return result
    @asynccontextmanager
    async def factory(settings, **options):
        assert len(engine_calls) == 9  # Both sides finish before coaching.
        class Coach(FakeCoach):
            async def analyze(self, fen, *, played_move=None, previous_move=None):
                coach_calls.append((played_move, settings.model))
                position = options['position_engine'](fen)
                move = options['engine'](None, position)
                assert position['fen'] == move['fen'] == fen
                assert move['played_move']['uci'] == played_move
                assert move['move_quality']['status'] in {'inaccuracy', 'mistake', 'blunder'}
                return await super().analyze(fen, played_move=played_move, previous_move=previous_move)
        yield Coach()
    async def run():
        service = GameAnalysisService(db, set(), engine, coach_factory=factory)
        await service.start(db.record['id'], 'alice', 'gpt-6.1-terra')
        await finish(service)
        row = await service.saved(db.record['id'], 'alice')
        assert row['status'] == 'completed'
        assert row['counts'] == {grade: 1 for grade in ('good', 'inaccuracy', 'mistake', 'blunder', 'uncertain')}
        assert row['coach_total'] == row['coach_completed'] == 3
        assert coach_calls == [(move, 'gpt-6.1-terra') for move in ('g1f3', 'f1c4', 'd2d3')]
        assert len(db.feedback) == 3
    asyncio.run(run())


def test_coach_failure_keeps_all_engine_results_and_resume_skips_saved_reviews():
    db = MemoryDatabase()
    engine_calls, coach_calls = [], []
    def engine(review):
        engine_calls.append(review.played_move_uci)
        return evidence(review)
    @asynccontextmanager
    async def factory(settings, **options):
        class Coach(FakeCoach):
            async def analyze(self, fen, *, played_move=None, previous_move=None):
                coach_calls.append(played_move)
                if len(coach_calls) == 2:
                    raise TimeoutError('private API diagnostics')
                return await super().analyze(fen, played_move=played_move, previous_move=previous_move)
        yield Coach()
    async def run():
        service = GameAnalysisService(db, set(), engine, coach_factory=factory)
        await service.start(db.record['id'], 'alice')
        await finish(service)
        row = await service.saved(db.record['id'], 'alice')
        assert row['status'] == 'failed' and row['completed'] == 4 and row['coach_completed'] == 1
        assert 'Coaching' in row['error'] and 'private' not in row['error']
        first = deepcopy(db.feedback)
        await service.start(db.record['id'], 'alice')
        await finish(service)
        row = await service.saved(db.record['id'], 'alice')
        assert row['status'] == 'completed' and row['coach_completed'] == 4
        assert all(db.feedback[key] == saved for key, saved in first.items())
        assert engine_calls == ['e2e4', 'g1f3', 'f1c4', 'e1g1', 'e7e5', 'b8c6', 'g8f6']
        assert coach_calls == ['e2e4', 'g1f3', 'g1f3', 'f1c4', 'e1g1']
    asyncio.run(run())


def test_legacy_completed_engine_job_can_add_coaching_and_reuse_manual_feedback():
    db = MemoryDatabase()
    game_id = db.record['id']
    fingerprint = pgn_fingerprint(db.record['pgn'])
    db.begin_game_analysis(game_id, 'white', fingerprint, 4)
    for ply in (0, 2, 4, 6):
        review = MoveReview.from_game(db.record['pgn'], ply)
        result = evidence(review)
        result['move_quality'] = assess_player_move(result['top_moves'][0], result['played_move'])
        db.save_game_analysis_move(game_id, 'white', fingerprint, ply,
                                   {'fen': review.position.fen, 'played_move': review.played_move_uci, 'stockfish': result})
    db.set_game_analysis_status(game_id, 'white', fingerprint, 'completed', None)
    original = deepcopy(db.rows[(game_id, 'white')]['moves'])
    calls = []
    @asynccontextmanager
    async def factory(settings, **options):
        calls.append(settings.model)
        yield FakeCoach()
    async def run():
        first = MoveReview.from_game(db.record['pgn'], 0)
        db.save_coach_feedback(await FakeCoach().analyze(first.position.fen, played_move=first.played_move_uci))
        def opponent_engine(review):
            assert review.position.side_to_move == 'Black', 'Saved player results must be reused'
            return evidence(review)
        service = GameAnalysisService(db, set(), opponent_engine, coach_factory=factory)
        started = await service.start(game_id, 'alice')
        assert started['status'] == 'queued' and started['coach_total'] == 4
        await finish(service)
        saved = await service.start(game_id, 'alice')
        assert saved['status'] == 'completed' and saved['coach_completed'] == 4
        assert db.rows[(game_id, 'white')]['moves'] == original and len(calls) == 3 and not service.tasks
    asyncio.run(run())


def test_background_coach_rejects_wrong_move_before_persistence():
    db = MemoryDatabase()
    @asynccontextmanager
    async def factory(settings, **options):
        class Coach(FakeCoach):
            async def analyze(self, fen, *, played_move=None, previous_move=None):
                return await super().analyze(fen, played_move='a2a3')
        yield Coach()
    async def run():
        service = GameAnalysisService(db, set(), evidence, coach_factory=factory)
        await service.start(db.record['id'], 'alice')
        await finish(service)
        saved = await service.saved(db.record['id'], 'alice')
        assert saved['status'] == 'failed' and saved['completed'] == 4
        assert saved['coach_completed'] == 0 and not db.feedback
    asyncio.run(run())


def test_manual_and_background_coach_share_one_generation_lock(monkeypatch):
    db = MemoryDatabase()
    monkeypatch.setattr('backend.main.Database', lambda _: db)
    entered, release = threading.Event(), threading.Event()
    @asynccontextmanager
    async def factory(settings, **options):
        class Coach(FakeCoach):
            async def analyze(self, fen, *, played_move=None, previous_move=None):
                entered.set()
                assert await asyncio.to_thread(release.wait, 5)
                return await super().analyze(fen, played_move=played_move, previous_move=previous_move)
        yield Coach()
    try:
        with TestClient(create_app('unused', game_engine=evidence, coach_factory=factory)) as client:
            game_id = db.record['id']
            assert client.post(f'/api/games/{game_id}/analysis', json={'username': 'alice', 'model': 'invalid'}).status_code == 422
            client.post(f'/api/games/{game_id}/analysis', json={'username': 'alice'})
            assert entered.wait(5)
            response = client.post('/api/coach/analyze', json={'game_id': game_id, 'ply': 0})
            assert response.status_code == 409
            release.set()
            assert wait_completed(client, game_id)['coach_completed'] == 4
    finally:
        release.set()


def test_completed_old_taxonomy_job_refreshes_only_stale_reviews_without_engine_work(test_db_url):
    db = Database(test_db_url)
    game = normalize_game(raw_game(), 'alice')
    db.save_import('alice', [game], 1)
    with TestClient(create_app(test_db_url, game_engine=evidence)) as client:
        client.post(f'/api/games/{game["id"]}/analysis', json={'username': 'alice'})
        assert wait_completed(client, game['id'])['coach_completed'] == 4
    with db.connection() as conn:
        conn.execute('UPDATE analysis_jobs SET coach_version=0')
        conn.execute("UPDATE game_moves SET coach_metadata=coach_metadata - 'classification_version' WHERE uci != 'e2e4'")
    before = db.game_analysis(game['id'], 'white', pgn_fingerprint(game['pgn']))['moves']
    calls = []
    @asynccontextmanager
    async def factory(settings, **options):
        class Coach(FakeCoach):
            async def analyze(self, fen, *, played_move=None, previous_move=None):
                calls.append(played_move)
                return await super().analyze(fen, played_move=played_move, previous_move=previous_move)
        yield Coach()
    with TestClient(create_app(test_db_url, game_engine=lambda _: pytest.fail('Must reuse engine results'), coach_factory=factory)) as client:
        summary = client.get('/api/games?username=alice').json()[0]['analysis']
        assert summary['coach_completed'] == 0 and summary['coach_total'] == 4
        client.post(f'/api/games/{game["id"]}/analysis', json={'username': 'alice'})
        result = wait_completed(client, game['id'])
        assert result['coach_completed'] == 4
        assert db.game_analysis(game['id'], 'white', pgn_fingerprint(game['pgn']))['moves'] == before
        assert calls == ['g1f3', 'f1c4', 'e1g1']
        client.post(f'/api/games/{game["id"]}/analysis', json={'username': 'alice'})
        assert len(calls) == 3  # Completed current reviews are reused.
    with db.connection() as conn:
        assert conn.execute('SELECT count(*) AS count FROM game_moves WHERE coach_metadata IS NOT NULL').fetchone()['count'] == 4
