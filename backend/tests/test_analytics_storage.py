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
from backend.coach.player_move_quality import PLAYER_QUALITY_POLICY
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


def test_coaching_preserves_objective_subcategory_raw_response_and_previous_success(test_db_url):
    db, game = imported(test_db_url)
    save_engine(db, game)
    review = MoveReview.from_game(game["pgn"], 0)
    raw = teaching_output()
    raw["move_evaluation"]["mistake_classification"] = {"category": "positional", "subcategory": "Improve"}
    exact = json.dumps(raw, indent=2) + "\n"
    normalized = deepcopy(raw)
    normalized["move_evaluation"]["mistake_classification"] = {"category": "positional", "subcategory": "Improve",
        "best_move_piece": "knight", "played_piece": "pawn", "same_piece": False}
    answer = CoachAnalysis("Saved explanation", "response-one", "test", review.position, None, played_move=review.played_move_uci,
        output_raw=exact, position_analysis={"structured": normalized, "coach_contract_version": COACH_CONTRACT_VERSION,
            "classification_version": CLASSIFICATION_VERSION, "sharpness_version": SHARPNESS_VERSION})
    db.save_coach_feedback(answer, game_id=game["id"], decision_ply=0)
    stored = move_row(db, game)
    assert stored["coach_output_raw"] == exact and stored["coach_error_category"] == "positional"
    assert "coach_decision_context" not in stored and stored["coach_error_subcategory"] == "Improve"
    restored = db.coach_feedback_for_reviews([(review.position.fen, review.played_move_uci)], game_id=game["id"])
    teaching = restored[(review.position.fen, review.played_move_uci)]["teaching"]
    assert "decision_context" not in teaching
    assert teaching["move_evaluation"]["mistake_classification"] == normalized["move_evaluation"]["mistake_classification"]
    db.save_coach_feedback(replace(answer, response_id="response-two"), game_id=game["id"], decision_ply=0)
    assert move_row(db, game)["move_id"] == stored["move_id"]
    with pytest.raises(ValueError):
        db.save_coach_feedback(replace(answer, output_raw="broken"), game_id=game["id"], decision_ply=0)
    assert move_row(db, game)["coach_metadata"]["response_id"] == "response-two"


def test_objective_migration_preserves_contexts_tactics_raw_text_piece_facts_and_reviews(test_db_url):
    db, game = imported(test_db_url)
    save_engine(db, game)
    review = db.start_review(game["id"], 0, 0)
    piece_facts = {"best_move_piece": "knight", "played_piece": "pawn", "same_piece": False}
    raw_responses = []
    with db.connection() as conn:
        # Recreate the previous schema, including labels absent from the new contract.
        conn.execute("ALTER TABLE game_moves DROP CONSTRAINT game_moves_coach_error_pair_check")
        conn.execute("ALTER TABLE game_moves DROP CONSTRAINT game_moves_coach_error_category_check")
        conn.execute("ALTER TABLE game_moves DROP CONSTRAINT game_moves_coach_error_subcategory_check")
        conn.execute("ALTER TABLE game_moves ADD COLUMN coach_decision_context TEXT")
        conn.execute("""ALTER TABLE game_moves ADD CONSTRAINT game_moves_coach_error_category_check
            CHECK (coach_error_category IN ('tactical_miss','tactical_allowed','other'))""")
        conn.execute("""ALTER TABLE game_moves ADD CONSTRAINT game_moves_coach_error_subcategory_check
            CHECK (coach_error_subcategory IN ('hanging_piece','fork','pin_skewer','discovered_attack'))""")
        for ply, objective in enumerate(['Attack', 'Defend', 'Improve', 'Convert', None, 'Attack', 'Improve']):
            category = 'other' if ply < 5 else 'tactical_miss' if ply == 5 else None
            subcategory = 'fork' if ply == 5 else None
            raw = teaching_output()
            raw['decision_context'] = objective
            raw['move_evaluation']['mistake_classification'] = {'category': category, 'subcategory': subcategory} if category else None
            raw_text = json.dumps(raw, indent=2) + '\n'
            raw_responses.append(raw_text)
            normalized = {'category': 'positional', 'subcategory': 'knight', **piece_facts} if ply < 5 else raw['move_evaluation']['mistake_classification']
            metadata = {'model': 'test', 'response_id': str(ply), 'text': 'Saved teaching', 'usage': None,
                        'generated_at': '2026-11-27T12:00:00+00:00', 'classification_version': 3,
                        'coach_contract_version': 7, 'normalized_classification': normalized}
            conn.execute("""UPDATE game_moves SET coach_error_category=%s, coach_error_subcategory=%s,
                coach_decision_context=%s, coach_metadata=%s, coach_output_raw=%s,
                coach_position_explanation='Saved position', coach_move_explanation='Saved move'
                WHERE game_id=%s AND decision_ply=%s""",
                (category, subcategory, objective, psycopg.types.json.Jsonb(metadata), raw_text, game['id'], ply))
        conn.execute("DELETE FROM schema_migrations WHERE name='coach_positional_objectives_v1'")

    # Standalone JSON reviews use the same labels and retain their original output.
    standalone = teaching_output()
    standalone['decision_context'] = 'Convert'
    standalone['move_evaluation']['mistake_classification'] = {'category': 'positional', 'subcategory': 'knight', **piece_facts}
    position = MoveReview.from_game(game['pgn'], 0).position
    db.save_coach_feedback(CoachAnalysis('Saved standalone', 'standalone', 'test', position, None,
        played_move='e2e4', position_analysis={'structured': standalone, 'classification_version': 3,
                                             'output_raw': raw_responses[3]}))
    engine_before = move_row(db, game)
    upgraded = Database(test_db_url)
    for ply, objective in enumerate(['Attack', 'Defend', 'Improve', 'Convert', None]):
        row = move_row(upgraded, game, ply)
        assert 'coach_decision_context' not in row
        assert row['coach_error_category'] == 'positional' and row['coach_error_subcategory'] == objective
        assert row['coach_output_raw'] == raw_responses[ply]
        assert {key: row['coach_metadata']['normalized_classification'][key] for key in piece_facts} == piece_facts
        classification = upgraded._coach_row(row)['teaching']['move_evaluation']['mistake_classification']
        assert classification == ({'category': 'positional', 'subcategory': objective, **piece_facts} if objective else None)
    for ply, category, subcategory in [(5, 'tactical_miss', 'fork'), (6, None, None)]:
        row = move_row(upgraded, game, ply)
        assert (row['coach_error_category'], row['coach_error_subcategory']) == (category, subcategory)
        assert row['coach_output_raw'] == raw_responses[ply]
    after = move_row(upgraded, game)
    assert {key: val for key, val in engine_before.items() if not key.startswith('coach_')} == {
        key: val for key, val in after.items() if not key.startswith('coach_')}
    assert upgraded.review_sessions(game['id'], 0) == [review]
    with upgraded.connection() as conn:
        saved = conn.execute("SELECT position_analysis FROM coach_feedback WHERE response_id='standalone'").fetchone()['position_analysis']
    assert saved['output_raw'] == raw_responses[3]
    assert 'decision_context' not in saved['structured']
    assert saved['structured']['move_evaluation']['mistake_classification'] == {
        'category': 'positional', 'subcategory': 'Convert', **piece_facts}
    # A later restart must neither repeat migration nor change a newly saved objective.
    with upgraded.connection() as conn:
        conn.execute("UPDATE game_moves SET coach_error_subcategory='Defend' WHERE decision_ply=0")
    assert move_row(Database(test_db_url), game)['coach_error_subcategory'] == 'Defend'


@pytest.mark.parametrize('category,subcategory', [
    ('other', None), ('positional', 'knight'), ('positional', 'fork'),
    ('tactical_miss', 'Attack'), ('tactical_allowed', None), (None, 'Improve'),
])
def test_database_rejects_retired_or_mismatched_error_labels(test_db_url, category, subcategory):
    db, game = imported(test_db_url)
    with pytest.raises(psycopg.errors.CheckViolation), db.connection() as conn:
        conn.execute('UPDATE game_moves SET coach_error_category=%s, coach_error_subcategory=%s WHERE game_id=%s',
                     (category, subcategory, game['id']))


@pytest.mark.parametrize("quality", ["best", "excellent", "good"])
def test_review_sessions_restart_repeat_idempotency_and_reset_guard(test_db_url, quality):
    db, game = imported(test_db_url)
    first, entry, fresh = db.reserve_review_submission(game["id"], 0, 0, "e2e4", "one")
    assert fresh and entry["grading_status"] == "pending"
    same, _, fresh = db.reserve_review_submission(game["id"], 0, 0, "e2e4", "one")
    assert not fresh and same["review_id"] == first["review_id"]
    db.finish_review_submission(game["id"], 0, 0, first["review_id"], "one", "mistake")
    db.reserve_review_submission(game["id"], 0, 0, "d2d4", "two", first["review_id"])
    done = db.finish_review_submission(game["id"], 0, 0, first["review_id"], "two", quality)
    assert done["status"] == "completed"
    assert [e["quality"] for e in done["tried_moves"]] == ["Mistake", quality.title()]
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


@pytest.mark.parametrize("quality", ["best", "excellent", "good"])
def test_practice_http_persists_failure_then_success_without_touching_original_engine(test_db_url, quality):
    db, game = imported(test_db_url)
    save_engine(db, game)
    before = move_row(db, game)
    app = FastAPI()
    app.state.db = db
    def grade(review, evidence):
        if review.played_move_uci == "e2e4":
            raise StockfishAnalysisError("private")
        return {"move_quality": {"status": quality, "winning_chances_loss_pp": 0}}
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
        assert response.json()["review"]["status"] == "completed"
        assert response.json()["review"]["tried_moves"][-1]["quality"] == quality.title()
        assert client.post(endpoint, json=payload).json()["accepted"]  # Safe network retry.
        assert len(client.get(endpoint).json()["review"]["tried_moves"]) == 2
    assert move_row(db, game) == before


def test_grade_upgrade_recalculates_once_preserving_evidence_and_review_history(test_db_url):
    db, game = imported(test_db_url)
    fingerprint = pgn_fingerprint(game["pgn"])
    db.begin_game_analysis(game["id"], "white", fingerprint, 4, 3)
    for ply, cp in enumerate([100, 90, 50]):
        review = MoveReview.from_game(game["pgn"], ply)
        stockfish = evidence(review)
        stockfish["played_move"]["score"]["cp"] = cp
        db.save_game_analysis_move(game["id"], "white", fingerprint, ply,
            {"fen": review.position.fen, "played_move": review.played_move_uci, "stockfish": stockfish})
    session, _, _ = db.reserve_review_submission(game["id"], 0, 0, "d2d4", "old-good")
    history = db.finish_review_submission(game["id"], 0, 0, session["review_id"], "old-good", "good")
    with db.connection() as conn:
        conn.execute("UPDATE game_moves SET move_quality='Good' WHERE engine_status='completed'")
        conn.execute("""UPDATE game_moves SET engine_search_metadata = jsonb_set(
            engine_search_metadata, '{policies,move_quality}', '{"legacy":true}') WHERE engine_status='completed'""")
        conn.execute("ALTER TABLE game_moves DROP CONSTRAINT game_moves_move_quality_check")
        conn.execute("""ALTER TABLE game_moves ADD CONSTRAINT game_moves_move_quality_check
            CHECK (move_quality IN ('Good','Inaccuracy','Mistake','Blunder','Uncertain'))""")
        conn.execute("DELETE FROM schema_migrations WHERE name='analytics_move_quality_best_excellent_v1'")
    before = [move_row(db, game, ply) for ply in range(7)]
    upgraded = Database(test_db_url)
    after = [move_row(upgraded, game, ply) for ply in range(7)]
    assert [row["move_quality"] for row in after] == ["Best", "Excellent", "Good", None, None, None, None]
    for old, new in zip(before, after):
        expected = deepcopy(old)
        if expected["engine_status"] == "completed":
            expected["move_quality"] = new["move_quality"]
            expected["engine_search_metadata"]["policies"]["move_quality"] = PLAYER_QUALITY_POLICY
        assert new == expected
    assert upgraded.review_sessions(game["id"], 0) == [history]
    counts = upgraded.game_analysis(game["id"], "white", fingerprint)["counts"]
    assert counts == upgraded.games("alice")[0]["analysis"]["counts"]
    assert counts == {"best": 1, "good": 1}
    # A normal restart must not run the backfill again.
    with upgraded.connection() as conn:
        conn.execute("UPDATE game_moves SET move_quality='Uncertain' WHERE decision_ply=0")
    assert move_row(Database(test_db_url), game)["move_quality"] == "Uncertain"


def test_black_exact_mate_tie_persists_as_best(test_db_url):
    db, game = imported(test_db_url)
    review = MoveReview.from_game(game["pgn"], 1)
    stockfish = evidence(review)
    stockfish["top_moves"][0]["score"] = {"cp": None, "mate": 5, "bound": "exact"}
    stockfish["played_move"]["score"] = {"cp": None, "mate": 5, "bound": "exact"}
    db.save_game_analysis_move(game["id"], "black", pgn_fingerprint(game["pgn"]), 1,
        {"fen": review.position.fen, "played_move": review.played_move_uci, "stockfish": stockfish})
    stored = move_row(db, game, 1)
    assert stored["top_1_mate"] == stored["played_mate"] == -5
    assert stored["move_quality"] == "Best"
    assert engine_result(stored)["stockfish"]["move_quality"]["status"] == "best"


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
