"""PostgreSQL repository. Each operation commits or rolls back as a unit."""
import json
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .coach.classification import CLASSIFICATION_VERSION
from .game_analysis import analysis_result, analysis_summary, coaching_total, pgn_fingerprint, quality_counts


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
            rows = db.execute(
                """SELECT g.metadata, g.pgn, a.game_id, a.player_color, a.pgn_hash, a.status,
                          a.total, a.completed, a.counts, a.coach_completed, a.coach_version, a.error, a.updated_at
                   FROM games g JOIN profile_games pg ON pg.game_id=g.id
                   LEFT JOIN game_engine_analysis a ON a.game_id=g.id AND a.player_color=
                       CASE WHEN lower(g.metadata->>'white')=%s THEN 'white' ELSE 'black' END
                   WHERE pg.username=%s ORDER BY g.end_time DESC, g.id""", (username, username))
            return [{**row["metadata"], "analysis": analysis_summary(row)
                     if row["pgn_hash"] == pgn_fingerprint(row["pgn"]) else None} for row in rows]

    def game(self, game_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT metadata, pgn FROM games WHERE id=%s", (game_id,)).fetchone()
            return {**row["metadata"], "pgn": row["pgn"]} if row else None

    def lesson_games(self, username: str) -> list[dict]:
        with self.connection() as db:
            return db.execute(
                """SELECT g.id, g.pgn, g.metadata, a.pgn_hash, a.moves
                   FROM games g JOIN profile_games pg ON pg.game_id=g.id
                   LEFT JOIN game_engine_analysis a ON a.game_id=g.id AND a.player_color=
                       CASE WHEN lower(g.metadata->>'white')=%s THEN 'white' ELSE 'black' END
                   WHERE pg.username=%s ORDER BY g.id""", (username, username)).fetchall()

    def game_analysis(self, game_id: str, color: str, fingerprint: str) -> dict | None:
        with self.connection() as db:
            return db.execute("SELECT * FROM game_engine_analysis WHERE game_id=%s AND player_color=%s AND pgn_hash=%s",
                              (game_id, color, fingerprint)).fetchone()

    def game_analyses(self, game_id: str, pgn: str) -> dict:
        with self.connection() as db:
            return {row["player_color"]: analysis_result(row) for row in db.execute(
                "SELECT * FROM game_engine_analysis WHERE game_id=%s AND pgn_hash=%s", (game_id, pgn_fingerprint(pgn)))}

    def interrupt_game_analyses(self):
        # A server restart preserves completed moves, but no old worker survives.
        with self.connection() as db:
            db.execute("""UPDATE game_engine_analysis SET status='interrupted',
                       error='Analysis paused when the app restarted. Resume to finish the remaining moves.',
                       updated_at=clock_timestamp() WHERE status IN ('queued', 'running')""")

    def begin_game_analysis(self, game_id: str, color: str, fingerprint: str, total: int) -> dict:
        with self.connection() as db:
            # Serialized by the service; the row lock also protects progress.
            row = db.execute("SELECT * FROM game_engine_analysis WHERE game_id=%s AND player_color=%s FOR UPDATE",
                             (game_id, color)).fetchone()
            if row and row["pgn_hash"] == fingerprint:
                if (row["status"] == "completed" and row["coach_completed"] >= coaching_total(row)
                        and row["coach_version"] == CLASSIFICATION_VERSION):
                    return row
                return db.execute("""UPDATE game_engine_analysis SET status='queued', error=NULL,
                                  coach_completed=CASE WHEN coach_version=%s THEN coach_completed ELSE 0 END,
                                  coach_version=%s, updated_at=clock_timestamp()
                                  WHERE game_id=%s AND player_color=%s RETURNING *""",
                                  (CLASSIFICATION_VERSION, CLASSIFICATION_VERSION, game_id, color)).fetchone()
            return db.execute("""INSERT INTO game_engine_analysis (game_id, player_color, pgn_hash, status, total, coach_version)
                              VALUES (%s, %s, %s, 'queued', %s, %s)
                              ON CONFLICT (game_id, player_color) DO UPDATE SET pgn_hash=excluded.pgn_hash,
                                  status='queued', total=excluded.total, completed=0, counts='{}', moves='{}', coach_completed=0, coach_version=excluded.coach_version,
                                  error=NULL, updated_at=clock_timestamp() RETURNING *""",
                              (game_id, color, fingerprint, total, CLASSIFICATION_VERSION)).fetchone()

    def save_game_analysis_move(self, game_id: str, color: str, fingerprint: str, ply: int, result: dict) -> bool:
        with self.connection() as db:
            row = db.execute("""UPDATE game_engine_analysis SET moves=moves || %s::jsonb,
                              updated_at=clock_timestamp() WHERE game_id=%s AND player_color=%s AND pgn_hash=%s
                              RETURNING moves""", (Jsonb({str(ply): result}), game_id, color, fingerprint)).fetchone()
            if row is None:
                return False
            db.execute("""UPDATE game_engine_analysis SET completed=%s, counts=%s
                       WHERE game_id=%s AND player_color=%s AND pgn_hash=%s""",
                       (len(row["moves"]), Jsonb(quality_counts(row["moves"])), game_id, color, fingerprint))
            return True

    def save_game_coach_progress(self, game_id: str, color: str, fingerprint: str, completed: int) -> bool:
        with self.connection() as db:
            return db.execute("""UPDATE game_engine_analysis SET coach_completed=GREATEST(coach_completed, %s),
                              updated_at=clock_timestamp() WHERE game_id=%s AND player_color=%s AND pgn_hash=%s""",
                              (completed, game_id, color, fingerprint)).rowcount > 0

    def set_game_analysis_status(self, game_id: str, color: str, fingerprint: str, status: str, error: str | None):
        with self.connection() as db:
            db.execute("""UPDATE game_engine_analysis SET status=%s, error=%s, updated_at=clock_timestamp()
                       WHERE game_id=%s AND player_color=%s AND pgn_hash=%s""",
                       (status, error, game_id, color, fingerprint))

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
                """INSERT INTO coach_feedback
                   (fen, text, model, response_id, usage, played_move, position_analysis, move_analysis, stockfish)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING fen, NULLIF(played_move, '') AS played_move, text, model, response_id, created_at, stockfish,
                             position_analysis -> 'classification_version' AS classification_version,
                             position_analysis -> 'sharpness_version' AS sharpness_version,
                             position_analysis -> 'structured' AS teaching,
                             position_analysis -> 'engine_evidence' AS position_evidence""",
                (analysis.position.fen, analysis.text, analysis.model, analysis.response_id,
                 Jsonb(analysis.usage) if analysis.usage is not None else None, analysis.played_move or '',
                 Jsonb(analysis.position_analysis) if analysis.position_analysis is not None else None,
                 Jsonb(analysis.move_analysis) if analysis.move_analysis is not None else None,
                 Jsonb(analysis.stockfish) if analysis.stockfish is not None else None),
            ).fetchone()

    def coach_feedback_for_positions(self, fens: list[str]) -> dict[str, dict]:
        rows = self.coach_feedback_for_reviews([(fen, None) for fen in fens])
        return {fen: row for (fen, _), row in rows.items()}

    def coach_feedback_for_reviews(self, reviews: list[tuple[str, str | None]]) -> dict[tuple[str, str | None], dict]:
        if not reviews:
            return {}
        with self.connection() as db:
            rows = db.execute(
                """SELECT DISTINCT ON (cf.fen, cf.played_move) cf.fen, NULLIF(cf.played_move, '') AS played_move,
                          text, model, response_id, created_at, stockfish, position_analysis -> 'classification_version' AS classification_version,
                             position_analysis -> 'sharpness_version' AS sharpness_version,
                             position_analysis -> 'structured' AS teaching,
                          position_analysis -> 'engine_evidence' AS position_evidence
                   FROM coach_feedback cf WHERE cf.fen = ANY(%s) AND cf.played_move = ANY(%s)
                   ORDER BY cf.fen, cf.played_move, created_at DESC, id DESC""",
                (list({fen for fen, _ in reviews}), list({move or '' for _, move in reviews})),
            ).fetchall()
            requested = set(reviews)
            return {(row["fen"], row["played_move"]): row for row in rows
                    if (row["fen"], row["played_move"]) in requested}
