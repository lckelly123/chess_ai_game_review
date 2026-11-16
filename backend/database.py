"""PostgreSQL repository. Each operation commits or rolls back as a unit."""
import json
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class Database:
    def __init__(self, conninfo: str = ""):
        # Empty conninfo uses standard PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE.
        self.conninfo = conninfo
        with self.connection() as db:
            db.execute("SELECT pg_advisory_xact_lock(7420918001)")
            db.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))

    @contextmanager
    def connection(self):
        with psycopg.connect(self.conninfo, row_factory=dict_row, connect_timeout=5) as db:
            yield db

    def health(self):
        with self.connection() as db:
            db.execute("SELECT 1")

    def save_import(self, username: str, games: list[dict], now: int) -> int:
        with self.connection() as db:
            db.execute("INSERT INTO profiles (username, last_synced) VALUES (%s, %s) ON CONFLICT(username) DO UPDATE SET last_synced=excluded.last_synced", (username, now))
            added = 0
            for game in games:
                metadata = {k: v for k, v in game.items() if k != "pgn"}
                db.execute("INSERT INTO games (id, url, pgn, metadata, end_time) VALUES (%s, %s, %s, %s, %s) ON CONFLICT(id) DO UPDATE SET pgn=excluded.pgn, metadata=excluded.metadata, end_time=excluded.end_time", (game["id"], game["url"], game["pgn"], Jsonb(metadata), game["end_time"]))
                cursor = db.execute("INSERT INTO profile_games (username, game_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (username, game["id"]))
                added += cursor.rowcount
            return added

    def profiles(self) -> list[dict]:
        with self.connection() as db:
            return db.execute("SELECT p.username, p.last_synced, COUNT(pg.game_id) AS game_count FROM profiles p LEFT JOIN profile_games pg USING(username) GROUP BY p.username ORDER BY p.last_synced DESC").fetchall()

    def games(self, username: str) -> list[dict]:
        with self.connection() as db:
            return [row["metadata"] for row in db.execute("SELECT g.metadata FROM games g JOIN profile_games pg ON pg.game_id=g.id WHERE pg.username=%s ORDER BY g.end_time DESC, g.id", (username,))]

    def game(self, game_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT metadata, pgn FROM games WHERE id=%s", (game_id,)).fetchone()
            return {**row["metadata"], "pgn": row["pgn"]} if row else None

    def cache(self, url: str) -> dict | None:
        with self.connection() as db:
            return db.execute("SELECT * FROM http_cache WHERE url=%s", (url,)).fetchone()

    def save_cache(self, url: str, body: dict, etag: str | None, modified: str | None, now: float):
        with self.connection() as db:
            db.execute("INSERT INTO http_cache (url, body, etag, modified, fetched) VALUES (%s, %s, %s, %s, %s) ON CONFLICT(url) DO UPDATE SET body=excluded.body, etag=excluded.etag, modified=excluded.modified, fetched=excluded.fetched", (url, json.dumps(body), etag, modified, now))

    def save_coach_feedback(self, analysis) -> dict:
        # Append successful generations; a failed rerun never erases an answer.
        with self.connection() as db:
            return db.execute(
                """INSERT INTO coach_feedback (fen, text, model, response_id, usage)
                   VALUES (%s, %s, %s, %s, %s)
                   RETURNING fen, text, model, response_id, created_at""",
                (analysis.position.fen, analysis.text, analysis.model, analysis.response_id,
                 Jsonb(analysis.usage) if analysis.usage is not None else None),
            ).fetchone()

    def coach_feedback_for_positions(self, fens: list[str]) -> dict[str, dict]:
        if not fens:
            return {}
        with self.connection() as db:
            rows = db.execute(
                """SELECT DISTINCT ON (fen) fen, text, model, response_id, created_at
                   FROM coach_feedback WHERE fen = ANY(%s)
                   ORDER BY fen, created_at DESC, id DESC""", (fens,),
            ).fetchall()
            return {row["fen"]: row for row in rows}
