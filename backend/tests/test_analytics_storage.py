"""The new storage contract: phase ownership, restart safety and real engine evidence."""
import json
from copy import deepcopy
from dataclasses import replace

import chess
import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.analysis_storage import engine_result
from backend.chess_games import normalize_game, replay
from backend.coach.move_review import MoveReview
from backend.coach.responses import CoachAnalysis
from backend.coach.context import COACH_CONTRACT_VERSION
from backend.coach.classification import CLASSIFICATION_VERSION
from backend.coach.sharpness import SHARPNESS_VERSION
from backend.coach.stockfish import StockfishSettings, StockfishAnalysisError
from backend.database import Database, ReviewConflict
from backend.game_analysis import analyze_game_move, analyze_final_position, pgn_fingerprint
from backend.game_statistics import build_statistics
from backend.ingestion import import_records
from backend.practice import create_practice_router
from backend.tests.test_app import raw_game
from backend.tests.test_coach import teaching_output
from backend.tests.test_game_analysis import evidence


def imported(url):
    db = Database(url)
    game = normalize_game(raw_game(rated=True, uuid="provider-one"), "alice")
    db.save_import("alice", [game], 100)
    return db, game


def move_row(db, game, ply=0):
    with db.connection() as conn:
        return conn.execute("SELECT * FROM game_moves WHERE game_id=%s AND decision_ply=%s", (game["id"], ply)).fetchone()


def save_engine(db, game, ply=0):
    review = MoveReview.from_game(game["pgn"], ply)
    result = {"fen": review.position.fen, "played_move": review.played_move_uci, "stockfish": evidence(review)}
    db.save_game_analysis_move(game["id"], "white", pgn_fingerprint(game["pgn"]), ply, result)
    return result


def test_initial_ingestion_is_complete_atomic_and_idempotent(test_db_url):
    db, game = imported(test_db_url)
    with db.connection() as conn:
        stored = conn.execute("SELECT * FROM games").fetchone()
        rows = conn.execute("SELECT * FROM game_moves ORDER BY decision_ply").fetchall()
        assert stored["raw_metadata"] == game["raw_metadata"]
        assert stored["rated"] is True and stored["source_game_id"] == "provider-one"
        assert stored["white_accuracy"] is stored["black_accuracy"] is None
        assert len(rows) == 7 and {r["color"] for r in rows} == {"white", "black"}
        assert all(r["engine_status"] == "not_run" and r["coach_metadata"] is None for r in rows)
        assert rows[0]["legal_moves_before"] == 20 and rows[0]["material_balance_before"] == 0
        assert rows[-1]["is_castling"]
    assert db.game_replay(game["id"])["positions"] == replay(game["pgn"])["positions"]
    save_engine(db, game)
    analyzed = move_row(db, game)
    assert db.save_import("alice", [game], 101) == 0
    assert move_row(db, game) == analyzed
    assert db.save_import("bob", [game], 102) == 1
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM games").fetchone()["n"] == 1
    invalid = {**game, "pgn": ""}
    before = db.profiles()
    with pytest.raises(ValueError):
        db.save_import("alice", [invalid], 1000)
    assert db.profiles() == before


def test_source_clock_precedence_missing_values_and_en_passant():
    pgn = '[TimeControl "60+2"]\n[UTCDate "2026.11.27"]\n[UTCTime "12:30:00"]\n\n1. e4 {[%clk 0:01:00]} a6 {[%clk 0:01:01]} 2. e5 {[%emt 0:00:03] [%clk 0:00:59]} d5 3. exd6 1-0'
    game = normalize_game(raw_game(pgn=pgn, time_control="60+2"), "alice")
    fields, moves = import_records(game, 100)
    assert fields["started_at"].isoformat() == "2026-11-27T12:30:00+00:00"
    assert moves[0]["time_spent_seconds"] == 2
    assert moves[1]["time_spent_seconds"] == 1
    assert moves[2]["time_spent_seconds"] == 3 and moves[2]["timing_source"] == "pgn_elapsed"
    assert moves[3]["time_spent_seconds"] is None and moves[3]["timing_status"] == "missing"
    assert moves[4]["captured_piece"] == "pawn" and moves[4]["is_capture"]
    _, unsupported = import_records(normalize_game(raw_game(time_control="1/86400"), "alice"), 100)
    assert unsupported[0]["time_spent_seconds"] is None and unsupported[0]["timing_status"] == "unsupported"


def test_black_scores_mates_bounds_and_candidate_reuse_roundtrip(test_db_url):
    db, game = imported(test_db_url)
    review = MoveReview.from_game(game["pgn"], 1)
    original = evidence(review)
    original["top_moves"][0].update(score={"cp": None, "mate": 5, "bound": "exact"})
    original["top_moves"][1]["score"]["bound"] = "lower"
    # Put the recorded move into the last candidate slot: played fields must reuse it.
    original["top_moves"][-1].update(uci=review.played_move_uci, san=review.played_move_san,
        pv_uci=[review.played_move_uci], pv_san=[review.played_move_san])
    result = {"fen": review.position.fen, "played_move": review.played_move_uci, "stockfish": original}
    db.save_game_analysis_move(game["id"], "black", pgn_fingerprint(game["pgn"]), 1, result)
    stored = move_row(db, game, 1)
    assert stored["top_1_cp"] is None and stored["top_1_mate"] == -5
    assert stored["top_2_cp"] == -90 and stored["top_2_bound"] == "upper"
    assert stored["played_cp"] == stored["top_5_cp"] == -60
    assert stored["played_depth"] == stored["top_5_depth"]
    assert stored["played_pv_uci"] == stored["top_5_pv_uci"]
    restored = engine_result(stored)
    assert restored["stockfish"]["top_moves"][0]["score"] == original["top_moves"][0]["score"]
    assert restored["stockfish"]["top_moves"][1]["score"] == original["top_moves"][1]["score"]
    assert stored["sharpness_score"] is None  # Bounded evidence is not a reliable sharpness measure.
    with pytest.raises(psycopg.errors.CheckViolation), db.connection() as conn:
        conn.execute("UPDATE game_moves SET top_1_cp=30 WHERE move_id=%s", (stored["move_id"],))


def test_coaching_preserves_raw_taxonomy_decision_context_and_previous_success(test_db_url):
    db, game = imported(test_db_url)
    save_engine(db, game)
    review = MoveReview.from_game(game["pgn"], 0)
    raw = teaching_output()
    raw["decision_context"] = "Improve"
    raw["move_evaluation"]["mistake_classification"] = {"category": "other", "subcategory": None}
    exact = json.dumps(raw, indent=2) + "\n"
    normalized = deepcopy(raw)
    normalized["move_evaluation"]["mistake_classification"] = {"category": "positional", "subcategory": "knight",
        "best_move_piece": "knight", "played_piece": "pawn", "same_piece": False}
    answer = CoachAnalysis("Saved explanation", "response-one", "test", review.position, None, played_move=review.played_move_uci,
        output_raw=exact, position_analysis={"structured": normalized, "coach_contract_version": COACH_CONTRACT_VERSION,
            "classification_version": CLASSIFICATION_VERSION, "sharpness_version": SHARPNESS_VERSION})
    db.save_coach_feedback(answer, game_id=game["id"], decision_ply=0)
    stored = move_row(db, game)
    assert stored["coach_output_raw"] == exact and stored["coach_error_category"] == "other"
    assert stored["coach_decision_context"] == "Improve" and stored["coach_error_subcategory"] is None
    db.save_coach_feedback(replace(answer, response_id="response-two"), game_id=game["id"], decision_ply=0)
    assert move_row(db, game)["move_id"] == stored["move_id"]
    with pytest.raises(ValueError):
        db.save_coach_feedback(replace(answer, output_raw="broken"), game_id=game["id"], decision_ply=0)
    assert move_row(db, game)["coach_metadata"]["response_id"] == "response-two"


def test_review_sessions_restart_repeat_idempotency_and_reset_guard(test_db_url):
    db, game = imported(test_db_url)
    first, entry, fresh = db.reserve_review_submission(game["id"], 0, 0, "e2e4", "one")
    assert fresh and entry["grading_status"] == "pending"
    same, _, fresh = db.reserve_review_submission(game["id"], 0, 0, "e2e4", "one")
    assert not fresh and same["review_id"] == first["review_id"]
    db.finish_review_submission(game["id"], 0, 0, first["review_id"], "one", "mistake")
    db.reserve_review_submission(game["id"], 0, 0, "d2d4", "two", first["review_id"])
    done = db.finish_review_submission(game["id"], 0, 0, first["review_id"], "two", "good")
    assert done["status"] == "completed"
    assert [e["quality"] for e in done["tried_moves"]] == ["Mistake", "Good"]
    restarted = Database(test_db_url)
    assert restarted.review_sessions(game["id"], 0) == [done]
    assert restarted.start_review(game["id"], 0, 0)["review_id"] == first["review_id"]
    second = restarted.start_review(game["id"], 0, 0, repeat=True)
    assert second["review_number"] == 2 and second["tried_moves"] == []
    restarted.reserve_review_submission(game["id"], 0, 0, "g1f3", "pending", second["review_id"])
    restarted.interrupt_game_analyses()
    assert restarted.review_sessions(game["id"], 0)[0]["tried_moves"][0]["grading_status"] == "failed"
    restarted.reset_analysis(game["id"])
    with pytest.raises(ReviewConflict):
        restarted.finish_review_submission(game["id"], 0, 0, second["review_id"], "pending", "good")
    assert restarted.review_sessions(game["id"], 0) == []


def test_practice_http_persists_failure_then_success_without_touching_original_engine(test_db_url):
    db, game = imported(test_db_url)
    save_engine(db, game)
    before = move_row(db, game)
    app = FastAPI()
    app.state.db = db
    def grade(review, evidence):
        if review.played_move_uci == "e2e4":
            raise StockfishAnalysisError("private")
        return {"move_quality": {"status": "good", "winning_chances_loss_pp": 0}}
    app.include_router(create_practice_router(grade))
    endpoint = f'/api/games/{game["id"]}/practice/0'
    with TestClient(app) as client:
        payload = {"fen": before["fen_before"], "original_move": before["uci"], "move": "e2e4", "submission_id": "failed"}
        assert client.post(endpoint, json=payload).status_code == 502
        data = client.get(endpoint).json()
        assert data["review"]["tried_moves"][0]["grading_status"] == "failed"
        payload.update(move="d2d4", submission_id="good")
        response = client.post(endpoint, json=payload)
        assert response.status_code == 200 and response.json()["accepted"]
        assert client.post(endpoint, json=payload).json()["accepted"]  # Safe network retry.
        assert len(client.get(endpoint).json()["review"]["tried_moves"]) == 2
    assert move_row(db, game) == before


def test_changed_pgn_invalidates_downstream_but_keeps_source_identity(test_db_url):
    db, game = imported(test_db_url)
    save_engine(db, game)
    old_id = move_row(db, game)["move_id"]
    db.start_review(game["id"], 0, 0)
    changed = normalize_game(raw_game(uuid="provider-one", pgn='1. d4 d5 1-0'), "alice")
    db.save_import("alice", [changed], 200)
    assert db.game(game["id"])["analysis_revision"] == 1
    assert move_row(db, game)["move_id"] != old_id
    assert move_row(db, game)["engine_status"] == "not_run"
    assert db.review_sessions(game["id"], 0) == []
    assert not db.save_game_analysis_move(game["id"], "white", pgn_fingerprint(game["pgn"]), 0, {})


def test_legacy_cutover_is_one_time_and_scoped_to_app_tables(test_db_url):
    with psycopg.connect(test_db_url) as conn:
        conn.execute("CREATE TABLE games(id TEXT PRIMARY KEY); INSERT INTO games VALUES ('discard'); CREATE TABLE unrelated(note TEXT); INSERT INTO unrelated VALUES ('keep')")
    db, game = imported(test_db_url)
    with db.connection() as conn:
        assert conn.execute("SELECT note FROM unrelated").fetchone()["note"] == "keep"
        assert conn.execute("SELECT COUNT(*) AS n FROM games").fetchone()["n"] == 1
        assert conn.execute("SELECT to_regclass('game_engine_analysis') AS old").fetchone()["old"] is None
    restarted = Database(test_db_url)
    assert restarted.game(game["id"])["pgn"] == game["pgn"]


def test_real_stockfish_roundtrip_complete_timeline_and_accuracy(test_db_url, monkeypatch):
    settings = StockfishSettings(depth=5, time_limit=0.3, threads=1, hash_mb=16)
    monkeypatch.setattr(StockfishSettings, "from_env", lambda: settings)
    db = Database(test_db_url)
    game = normalize_game(raw_game(pgn='1. f3 e5 2. g4 Qh4# 0-1'), "alice")
    db.save_import("alice", [game], 100)
    fingerprint = pgn_fingerprint(game["pgn"])
    db.begin_game_analysis(game["id"], "white", fingerprint, 2, 2)
    results = {}
    for ply in range(4):
        review = MoveReview.from_game(game["pgn"], ply)
        raw = analyze_game_move(review)
        position = raw.pop("position_evidence")
        result = {"fen": review.position.fen, "played_move": review.played_move_uci, "stockfish": raw, "position_evidence": position}
        db.save_game_analysis_move(game["id"], "white", fingerprint, ply, result)
        results[str(ply)] = engine_result(move_row(db, game, ply))
        for a, b in zip(result["stockfish"]["top_moves"], results[str(ply)]["stockfish"]["top_moves"]):
            assert a["uci"] == b["uci"] and a["score"] == b["score"] and a["pv_uci"] == b["pv_uci"]
    final = analyze_final_position(game["pgn"])
    stats = build_statistics(replay(game["pgn"]), results, final)
    assert db.save_game_statistics(game["id"], "white", fingerprint, stats)
    saved = db.game_analysis(game["id"], "white", fingerprint)
    assert saved["statistics"]["complete"] and saved["statistics"]["accuracy"] == stats["accuracy"]
    assert all(0 <= n <= 100 for n in stats["accuracy"].values())
    assert move_row(db, game, 3)["engine_final_position"]["mate_winner"] == "black"
    assert move_row(db, game, 3)["engine_final_position"]["mate"] == 0


def test_failed_coach_keeps_engine_phase_and_never_saves_partial_response(test_db_url):
    import httpx2
    from backend.main import create_app
    from backend.tests.test_coach_routes import mock_coach_factory
    from backend.tests.test_move_coach import evidence as coach_evidence
    db, game = imported(test_db_url)
    factory = mock_coach_factory(lambda request: httpx2.Response(500, json={"error": {"message": "test failure"}}), engine=coach_evidence)
    with TestClient(create_app(test_db_url, coach_factory=factory)) as client:
        response = client.post('/api/coach/analyze', json={"game_id": game["id"], "ply": 0})
        assert response.status_code == 502
    row = move_row(db, game)
    assert row["engine_status"] == "completed" and row["move_quality"] is not None
    assert row["coach_output_raw"] is row["coach_metadata"] is None
