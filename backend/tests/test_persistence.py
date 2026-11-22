import hashlib
import json
import shutil
import sqlite3
from copy import deepcopy

import chess
import httpx2
import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.chess_games import normalize_game
from backend.coach import CoachAnalysis, CoachPosition
from backend.database import Database
from backend.main import create_app
from backend.migrate_sqlite import MIGRATION, migrate_sqlite
from backend.tests.test_app import raw_game
from backend.tests.test_coach import completed_response, teaching_output
from backend.tests.test_coach_routes import mock_coach_factory


def legacy_database(path, *, broken=False):
    game = normalize_game(raw_game(99), "alice")
    metadata = {key: value for key, value in game.items() if key != "pgn"}
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE games (id TEXT PRIMARY KEY, url TEXT, pgn TEXT, metadata TEXT, end_time INTEGER);
            CREATE TABLE profiles (username TEXT PRIMARY KEY, last_synced INTEGER);
            CREATE TABLE profile_games (username TEXT, game_id TEXT, PRIMARY KEY(username, game_id));
            CREATE TABLE http_cache (url TEXT PRIMARY KEY, body TEXT, etag TEXT, modified TEXT, fetched REAL);
        """)
        db.execute("INSERT INTO profiles VALUES (?, ?)", ("alice", 123))
        db.execute("INSERT INTO games VALUES (?, ?, ?, ?, ?)", (game["id"], game["url"], game["pgn"], json.dumps(metadata), game["end_time"]))
        db.execute("INSERT INTO profile_games VALUES (?, ?)", ("alice", "missing" if broken else game["id"]))
        db.execute("INSERT INTO http_cache VALUES (?, ?, ?, ?, ?)", ("https://api.chess.com/pub/player/alice", '{"username":"alice"}', '"etag"', None, 123.5))
    return game


def test_sqlite_migration_is_complete_read_only_and_idempotent(test_db_url, tmp_path):
    source = tmp_path / "legacy.db"
    game = legacy_database(source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    db = Database(test_db_url)
    assert migrate_sqlite(db, source) == {"profiles": 1, "games": 1, "profile_games": 1, "http_cache": 1}
    assert db.game(game["id"]) == game
    assert db.profiles() == [{"username": "alice", "last_synced": 123, "game_count": 1}]
    assert db.cache("https://api.chess.com/pub/player/alice")["etag"] == '"etag"'
    db.save_import("alice", [game], 456)
    assert migrate_sqlite(db, source) == {}
    assert db.profiles()[0]["last_synced"] == 456
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_broken_migration_rolls_back_all_records_and_marker(test_db_url, tmp_path):
    source = tmp_path / "broken.db"
    legacy_database(source, broken=True)
    db = Database(test_db_url)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        migrate_sqlite(db, source)
    assert db.profiles() == []
    with db.connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM games").fetchone()["n"] == 0
        assert conn.execute("SELECT name FROM schema_migrations WHERE name=%s", (MIGRATION,)).fetchone() is None


def test_read_only_wal_source_keeps_uncheckpointed_records(test_db_url, tmp_path):
    original = tmp_path / "original.db"
    legacy_database(original)
    snapshot_dir = tmp_path / "readonly"
    snapshot_dir.mkdir()
    snapshot = snapshot_dir / "chess.db"
    with sqlite3.connect(original) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("UPDATE profiles SET last_synced=987")
        writer.commit()
        # A stable offline snapshot with WAL but no shared-memory index.
        shutil.copyfile(original, snapshot)
        shutil.copyfile(str(original) + "-wal", str(snapshot) + "-wal")
    before = {p.name: p.read_bytes() for p in snapshot_dir.iterdir()}
    snapshot_dir.chmod(0o555)
    try:
        db = Database(test_db_url)
        migrate_sqlite(db, snapshot)
        assert db.profiles()[0]["last_synced"] == 987
        assert {p.name: p.read_bytes() for p in snapshot_dir.iterdir()} == before
    finally:
        snapshot_dir.chmod(0o755)


def test_feedback_restores_after_restart_and_is_position_specific(test_db_url):
    calls = []
    db = Database(test_db_url)
    game = normalize_game(raw_game(), "alice")
    db.save_import("alice", [game], 123)
    def upstream(request):
        calls.append(request)
        return httpx2.Response(200, json=completed_response(request=request))
    factory = mock_coach_factory(upstream)
    with TestClient(create_app(test_db_url, coach_factory=factory)) as client:
        detail = client.get(f'/api/games/{game["id"]}').json()
        fen = detail["positions"][1]["fen"]
        assert client.get('/api/coach/feedback', params={"fen": fen}).json() is None
        saved = client.post('/api/coach/analyze', json={"fen": fen}).json()
        assert saved["created_at"] and saved["text"]
        assert set(saved["teaching"]) == {"positional_thesis", "candidate_moves", "move_evaluation"}
        assert "Needs of the Position" not in saved["text"]
        with db.connection() as conn:
            structured = conn.execute("SELECT position_analysis -> 'structured' AS teaching FROM coach_feedback").fetchone()["teaching"]
            assert structured == saved["teaching"]
    with TestClient(create_app(test_db_url, coach_factory=factory)) as restarted:
        assert restarted.get('/api/coach/feedback', params={"fen": fen}).json() == saved
        detail = restarted.get(f'/api/games/{game["id"]}').json()
        assert detail["coach_responses"] == {"1": saved}
        assert restarted.get('/api/coach/feedback', params={"fen": chess.STARTING_FEN}).json() is None
        assert restarted.get('/api/coach/feedback', params={"fen": "invalid"}).status_code == 422
    assert len(calls) == 1  # Reading/reopening never generates another paid answer.


def test_retired_needs_migration_preserves_history_and_runs_once(test_db_url):
    db = Database(test_db_url)
    position = CoachPosition.from_fen(chess.STARTING_FEN)
    current = teaching_output()
    legacy = {**current, "needs_of_position": "Archived planning paragraph."}
    for index, payload in enumerate([
        None,
        {"structured": None},
        {"structured": current},
        {"structured": legacy, "engine_evidence": {"top_moves": []},
         "classification_version": 2, "text": json.dumps(legacy)},
    ]):
        db.save_coach_feedback(CoachAnalysis(
            "Archived response text", f"resp_{index}", "model", position, {"total_tokens": 10},
            position_analysis=payload,
        ))
    with db.connection() as conn:
        before = conn.execute("SELECT * FROM coach_feedback ORDER BY id").fetchall()
        # Simulate an existing database before this migration was introduced.
        conn.execute("DELETE FROM schema_migrations WHERE name = 'coach_remove_needs_of_position_v1'")

    migrated = Database(test_db_url)
    expected = deepcopy(before)
    del expected[-1]["position_analysis"]["structured"]["needs_of_position"]
    with migrated.connection() as conn:
        assert conn.execute("SELECT * FROM coach_feedback ORDER BY id").fetchall() == expected
        marker = conn.execute("SELECT * FROM schema_migrations WHERE name = 'coach_remove_needs_of_position_v1'").fetchone()
        assert marker is not None
        versions = conn.execute("SELECT xmin::text AS version FROM coach_feedback ORDER BY id").fetchall()

    restarted = Database(test_db_url)
    with restarted.connection() as conn:
        assert conn.execute("SELECT * FROM coach_feedback ORDER BY id").fetchall() == expected
        assert conn.execute("SELECT xmin::text AS version FROM coach_feedback ORDER BY id").fetchall() == versions
        assert conn.execute("SELECT * FROM schema_migrations WHERE name = 'coach_remove_needs_of_position_v1'").fetchone() == marker
    with TestClient(create_app(test_db_url)) as client:
        response = client.get('/api/coach/feedback', params={"fen": position.fen})
        assert response.status_code == 200
        assert response.json()["teaching"] == current
        assert response.json()["text"] == "Archived response text"


def test_reruns_keep_history_and_failed_generation_preserves_latest(test_db_url):
    db = Database(test_db_url)
    position = CoachPosition.from_fen(chess.STARTING_FEN)
    first = db.save_coach_feedback(CoachAnalysis("First", "resp_1", "model", position, {"total_tokens": 10}))
    latest = db.save_coach_feedback(CoachAnalysis("Second", "resp_2", "model", position, None))
    assert db.coach_feedback_for_positions([position.fen])[position.fen] == latest
    with db.connection() as conn:
        rows = conn.execute("SELECT text, usage FROM coach_feedback ORDER BY id").fetchall()
        assert rows == [{"text": "First", "usage": {"total_tokens": 10}}, {"text": "Second", "usage": None}]
    factory = mock_coach_factory(lambda request: httpx2.Response(500, json={"error": {"message": "upstream failure"}}))
    with TestClient(create_app(test_db_url, coach_factory=factory)) as client:
        assert client.post('/api/coach/analyze', json={"fen": position.fen}).status_code == 502
    assert db.coach_feedback_for_positions([position.fen])[position.fen] == latest
    assert first["created_at"] <= latest["created_at"]


def test_database_failures_are_safe_and_do_not_claim_saved_feedback(test_db_url, monkeypatch):
    calls = []
    def upstream(request):
        calls.append(request)
        return httpx2.Response(200, json=completed_response())
    app = create_app(test_db_url, coach_factory=mock_coach_factory(upstream))
    with TestClient(app) as client:
        def fail(*args):
            raise psycopg.OperationalError("secret connection detail")
        monkeypatch.setattr(app.state.db, "save_coach_feedback", fail)
        result = client.post('/api/coach/analyze', json={"fen": chess.STARTING_FEN})
        assert result.status_code == 503
        assert "could not be saved" in result.json()["detail"]
        assert "secret" not in result.text
        assert client.get('/api/coach/feedback', params={"fen": chess.STARTING_FEN}).json() is None
        monkeypatch.setattr(app.state.db, "health", fail)
        result = client.post('/api/coach/analyze', json={"fen": chess.STARTING_FEN})
        assert result.status_code == 503 and "secret" not in result.text
        assert len(calls) == 1
