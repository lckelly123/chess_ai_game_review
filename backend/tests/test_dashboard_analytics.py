from copy import deepcopy

import chess
import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.analytics import aggregate_moves, empty_summary, position_outlook, preferred_piece, TABLES
from backend.chess_games import normalize_game
from backend.coach.classification import CLASSIFICATION_VERSION
from backend.coach.move_review import MoveReview
from backend.coach.responses import CoachAnalysis
from backend.database import Database
from backend.game_analysis import pgn_fingerprint
from backend.main import create_app
from backend.tests.test_app import raw_game
from backend.tests.test_coach import teaching_output
from backend.tests.test_game_analysis import evidence


def decision(**overrides):
    return {"time_class": "rapid", "time_control_raw": "600", "engine_status": "completed",
        "engine_pgn_hash": "current", "pgn_hash": "current", "move_quality": "Mistake",
        "phase_before": "opening", "sharpness_classification": "Flexible", "color": "white",
        "top_1_cp": 100, "top_1_mate": None, "top_1_bound": "exact", "top_1_depth": 12,
        "top_1_uci": "g1f3", "fen_before": chess.STARTING_FEN, "piece_moved": "pawn",
        "classification_version": CLASSIFICATION_VERSION, "coach_error_category": "positional",
        "coach_error_subcategory": "Improve", **overrides}


@pytest.mark.parametrize("cp,expected", [(-301, "Losing"), (-300, "Worse"), (-51, "Worse"),
    (-50, "Equal"), (0, "Equal"), (50, "Equal"), (51, "Better"), (300, "Better"), (301, "Winning")])
def test_outlook_boundaries_and_black_orientation(cp, expected):
    assert position_outlook(decision(top_1_cp=cp)) == expected
    assert position_outlook(decision(top_1_cp=-cp, color="black")) == expected


def test_mates_and_missing_or_bounded_outlook():
    assert position_outlook(decision(top_1_cp=None, top_1_mate=3)) == "Winning"
    assert position_outlook(decision(top_1_cp=None, top_1_mate=3, color="black")) == "Losing"
    for changes in ({"top_1_bound": "lower"}, {"top_1_depth": 0}, {"top_1_cp": None},
                    {"top_1_cp": None, "top_1_mate": 0}):
        assert position_outlook(decision(**changes)) is None


def test_separate_populations_denominators_matrices_and_time_controls():
    moves = [decision(), decision(move_quality="Good"), decision(move_quality="Uncertain"),
        decision(engine_status="not_run"), decision(engine_pgn_hash="old"),
        decision(sharpness_classification=None, classification_version=None),
        decision(top_1_bound="lower", coach_error_subcategory="Attack"),
        decision(coach_error_category="tactical_miss", coach_error_subcategory="fork"),
        decision(time_class="blitz", time_control_raw="180+2", coach_error_category="tactical_allowed",
                 coach_error_subcategory="hanging_piece")]
    before = deepcopy(moves)
    groups = aggregate_moves(moves)
    rapid = groups[("rapid", "600")]
    assert rapid["phase"]["opening_moves"] == 5
    assert rapid["phase"]["opening_errors"] == 4
    assert rapid["sharpness"]["flexible_moves"] == 4
    assert rapid["outlook"]["better_moves"] == 4
    assert rapid["decision_context"] == {"attack_count": 1, "defend_count": 0, "improve_count": 1, "convert_count": 0}
    assert rapid["piece_comparison"]["counts"]["pawn"]["knight"] == 1
    assert rapid["context_outlook"]["counts"]["Better"]["Improve"] == 1
    assert rapid["context_outlook"]["counts"]["Better"]["Attack"] == 0
    assert rapid["tactical"]["fork_missed"] == 1
    assert groups[("blitz", "180+2")]["tactical"]["hanging_piece_allowed"] == 1
    assert moves == before


def test_piece_identity_before_promotion_or_castling_and_missing_historical_objective():
    assert preferred_piece(decision(fen_before="7k/P7/8/8/8/8/8/7K w - - 0 1", top_1_uci="a7a8q")) == "pawn"
    assert preferred_piece(decision(fen_before="4k3/8/8/8/8/8/8/4K2R w K - 0 1", top_1_uci="e1g1")) == "king"
    group = aggregate_moves([decision(coach_error_subcategory=None)])[("rapid", "600")]
    assert sum(group["decision_context"].values()) == 0
    assert group["piece_comparison"]["counts"]["pawn"]["knight"] == 1


def save_move(db, game, ply=0):
    review = MoveReview.from_game(game["pgn"], ply)
    db.save_game_analysis_move(game["id"], review.position.side_to_move.lower(), pgn_fingerprint(game["pgn"]), ply,
        {"fen": review.position.fen, "played_move": review.played_move_uci, "stockfish": evidence(review)})
    return review


def save_coach(db, game, review):
    teaching = teaching_output()
    teaching["move_evaluation"]["mistake_classification"] = {"category": "positional", "subcategory": "Improve"}
    db.save_coach_feedback(CoachAnalysis("Review", "test-response", "test", review.position, None,
        played_move=review.played_move_uci,
        position_analysis={"structured": teaching, "classification_version": CLASSIFICATION_VERSION}),
        game_id=game["id"], decision_ply=0)


def test_storage_hooks_are_player_scoped_idempotent_and_resettable(test_db_url):
    db = Database(test_db_url)
    rapid = normalize_game(raw_game(1), "alice")
    blitz = normalize_game(raw_game(2, time_class="blitz", time_control="180+2"), "alice")
    db.save_import("alice", [rapid, blitz], 100)
    db.save_import("bob", [rapid], 100)
    db.save_import("outsider", [rapid], 100)
    assert db.analytics("outsider")["time_controls"] == []
    assert len(db.analytics("alice")["time_controls"]) == 2
    review = save_move(db, rapid)
    save_move(db, rapid, 1)
    save_move(db, rapid)  # Saving the same decision twice never doubles counts.
    save_coach(db, rapid, review)
    save_coach(db, rapid, review)
    summary = db.analytics("alice", refresh=True)
    group = next(row for row in summary["time_controls"] if row["time_class"] == "rapid")
    assert group["phase"]["opening_moves"] == group["phase"]["opening_errors"] == 1
    assert group["decision_context"]["improve_count"] == 1
    assert db.analytics("bob")["time_controls"][0]["phase"]["opening_moves"] == 1
    assert db.analytics("bob")["time_controls"][0]["decision_context"]["improve_count"] == 0
    with db.connection() as conn:
        for name in TABLES:
            rows = conn.execute(f"SELECT * FROM analytics_{name} WHERE username='alice'").fetchall()
            assert len(rows) == 2
            assert all(row["updated_at"] == summary["updated_at"] for row in rows)
    db.reset_analysis(rapid["id"])
    assert all(row["phase"]["opening_moves"] == 0 for row in db.analytics("alice")["time_controls"])
    assert db.analytics("bob")["time_controls"][0]["phase"]["opening_moves"] == 0


def test_reimport_removes_obsolete_controls_and_startup_backfills(test_db_url):
    db = Database(test_db_url)
    game = normalize_game(raw_game(), "alice")
    db.save_import("alice", [game], 100)
    save_move(db, game)
    changed = normalize_game(raw_game(time_control="180+2", time_class="blitz"), "alice")
    db.save_import("alice", [changed], 101)
    snapshot = db.analytics("alice")
    assert len(snapshot["time_controls"]) == 1
    assert snapshot["time_controls"][0]["time_control_raw"] == "180+2"
    with db.connection() as conn:
        for name in TABLES:
            conn.execute(f"DELETE FROM analytics_{name}")
        conn.execute("DELETE FROM schema_migrations WHERE name='dashboard_analytics_v1'")
    assert Database(test_db_url).analytics("alice")["time_controls"] == snapshot["time_controls"]


def test_failed_rebuild_rolls_back_all_seven_tables(test_db_url, monkeypatch):
    db = Database(test_db_url)
    db.save_import("alice", [normalize_game(raw_game(), "alice")], 100)
    before = db.analytics("alice")
    broken = empty_summary()
    broken["phase"]["opening_errors"] = -1
    monkeypatch.setattr("backend.analytics.aggregate_moves", lambda _: {("rapid", "600"): broken})
    with pytest.raises(psycopg.errors.CheckViolation):
        db.analytics("alice", refresh=True)
    assert db.analytics("alice") == before


def test_api_refresh_reads_only_saved_data_and_validates_usernames(test_db_url):
    def external(request):
        pytest.fail("Analytics must never contact an external service")
    with TestClient(create_app(test_db_url, httpx.MockTransport(external))) as client:
        assert client.get("/api/analytics?username=alice").json()["time_controls"] == []
        assert client.post("/api/analytics/refresh?username=alice").status_code == 200
        assert client.post("/api/analytics/refresh?username=bad%20name").status_code == 422
