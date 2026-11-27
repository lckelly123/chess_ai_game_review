"""Transactional repositories for the four data collection phases."""
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import chess
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .analysis_storage import engine_columns, engine_result, derived_columns, orient_evidence
from .ingestion import import_records, game_api
from .chess_games import replay
from .coach.context import COACH_CONTRACT_VERSION, context_key
from .coach.player_move_quality import ACCEPTABLE_STATUSES, PLAYER_QUALITY_POLICY
from .game_analysis import analysis_result, analysis_summary, coaching_total, pgn_fingerprint, quality_counts
from .game_statistics import STATISTICS_VERSION, build_statistics

MULTI_GAME_COLUMNS = """id, username, status, input_snapshot -> 'summary' AS summary,
                       report, model, reasoning_effort, response_id, error, created_at, updated_at"""


def value(item):
    return Jsonb(item) if isinstance(item, (dict, list)) else item


def insert(db, table, fields, suffix=""):
    return db.execute(sql.SQL("INSERT INTO {} ({}) VALUES ({}) " + suffix).format(
        sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, fields)),
        sql.SQL(",").join(sql.Placeholder() for _ in fields)), [value(item) for item in fields.values()])


def update(db, table, fields, where, params):
    return db.execute(sql.SQL("UPDATE {} SET {} WHERE " + where).format(sql.Identifier(table),
        sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(key)) for key in fields)),
        [*[value(item) for item in fields.values()], *params])


class ReviewConflict(ValueError):
    pass


class Database:
    def __init__(self, conninfo: str = ""):
        self.conninfo = conninfo
        with self.connection() as db:
            db.execute("SELECT pg_advisory_xact_lock(7420918001)")
            db.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
            self._upgrade_move_quality(db)

    @staticmethod
    def _upgrade_move_quality(db):
        """Regrade saved evidence once, under the startup transaction/lock."""
        migration = "analytics_move_quality_best_excellent_v1"
        if db.execute("SELECT 1 FROM schema_migrations WHERE name=%s", (migration,)).fetchone():
            return
        db.execute("ALTER TABLE game_moves DROP CONSTRAINT game_moves_move_quality_check")
        db.execute("""ALTER TABLE game_moves ADD CONSTRAINT game_moves_move_quality_check
            CHECK (move_quality IN ('Best','Excellent','Good','Inaccuracy','Mistake','Blunder','Uncertain'))""")
        rows = db.execute("""SELECT m.* FROM game_moves m JOIN games g USING(game_id)
            WHERE m.engine_status='completed' AND m.engine_pgn_hash=g.pgn_hash""")
        for row in rows:
            quality = engine_result(row)["stockfish"]["move_quality"]["status"]
            metadata = row["engine_search_metadata"] or {}
            metadata["policies"] = {**metadata.get("policies", {}), "move_quality": PLAYER_QUALITY_POLICY}
            update(db, "game_moves", {"move_quality": quality.title(), "engine_search_metadata": metadata},
                   "move_id=%s", [row["move_id"]])
        db.execute("INSERT INTO schema_migrations(name) VALUES (%s)", (migration,))

    @contextmanager
    def connection(self):
        with psycopg.connect(self.conninfo, row_factory=dict_row, connect_timeout=5) as db:
            yield db

    def health(self):
        with self.connection() as db:
            db.execute("SELECT 1")

    def save_import(self, username, games, now):
        with self.connection() as db:
            db.execute("INSERT INTO profiles VALUES (%s,%s) ON CONFLICT(username) DO UPDATE SET last_synced=excluded.last_synced", (username, now))
            added = 0
            for record in games:
                fields, moves = import_records(record, now)
                db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (fields["source_url"],))
                existing = db.execute("""SELECT * FROM games WHERE source=%s AND
                    (source_game_id=%s OR source_url=%s) FOR UPDATE""",
                    (fields["source"], fields["source_game_id"], fields["source_url"])).fetchone()
                game_id = existing["game_id"] if existing else fields["game_id"]
                changed = existing and existing["pgn_hash"] != fields["pgn_hash"]
                fields["game_id"] = game_id
                if existing:
                    fields.pop("imported_at")
                    if changed:
                        self._clear_analysis(db, [game_id])
                        db.execute("DELETE FROM game_moves WHERE game_id=%s", (game_id,))
                    update(db, "games", fields, "game_id=%s", [game_id])
                else:
                    insert(db, "games", fields)
                for move in moves:
                    move["game_id"] = game_id
                    if existing and not changed:
                        update(db, "game_moves", move, "game_id=%s AND decision_ply=%s", [game_id, move["decision_ply"]])
                    else:
                        insert(db, "game_moves", move)
                added += db.execute("INSERT INTO profile_games VALUES (%s,%s) ON CONFLICT DO NOTHING", (username, game_id)).rowcount
            return added

    def profiles(self):
        with self.connection() as db:
            return db.execute("SELECT p.username,p.last_synced,COUNT(pg.game_id) AS game_count FROM profiles p LEFT JOIN profile_games pg USING(username) GROUP BY p.username ORDER BY p.last_synced DESC").fetchall()

    def game_sync_window(self, username):
        with self.connection() as db:
            return db.execute("""SELECT EXTRACT(EPOCH FROM MIN(g.ended_at))::bigint AS oldest,
                EXTRACT(EPOCH FROM MAX(g.ended_at))::bigint AS newest,p.last_synced
                FROM profiles p LEFT JOIN profile_games pg USING(username) LEFT JOIN games g USING(game_id)
                WHERE p.username=%s GROUP BY p.last_synced""", (username,)).fetchone() or {"oldest": None, "newest": None, "last_synced": None}

    @staticmethod
    def _game_rows(db, username=None):
        return db.execute("""SELECT g.*,(SELECT COUNT(*) FROM game_moves m WHERE m.game_id=g.game_id) AS ply_count
            FROM games g WHERE %s::text IS NULL OR EXISTS
            (SELECT 1 FROM profile_games p WHERE p.game_id=g.game_id AND p.username=%s)
            ORDER BY ended_at DESC,game_id""", (username, username)).fetchall()

    def games(self, username):
        with self.connection() as db:
            result = []
            for row in self._game_rows(db, username):
                color = "white" if row["white_username"].lower() == username else "black"
                game = game_api(row, row["ply_count"])
                game.pop("pgn")
                result.append({**game, "analysis": analysis_summary(self._job_summary(db, row, color))})
            return result

    def game(self, game_id):
        with self.connection() as db:
            row = db.execute("""SELECT g.*,(SELECT COUNT(*) FROM game_moves m WHERE m.game_id=g.game_id) AS ply_count
                FROM games g WHERE game_id=%s""", (game_id,)).fetchone()
            return game_api(row, row["ply_count"]) if row else None

    def game_replay(self, game_id):
        """Reopen the board using saved phase 1 rows."""
        from .game_phase import next_phase
        with self.connection() as db:
            game = db.execute("SELECT * FROM games WHERE game_id=%s", (game_id,)).fetchone()
            if not game:
                return None
            rows = db.execute("SELECT * FROM game_moves WHERE game_id=%s ORDER BY decision_ply", (game_id,)).fetchall()
        def position(fen, last, phase):
            board = chess.Board(fen)
            return {"fen": fen, "last_move": last, "phase": phase,
                    "check_square": chess.square_name(board.king(board.turn)) if board.is_check() else None}
        positions = [position(game["initial_fen"], None, rows[0]["phase_before"] if rows else next_phase(chess.Board(game["initial_fen"])))]
        moves = []
        for row in rows:
            moves.append({"ply": row["decision_ply"]+1, "san": row["san"], "uci": row["uci"], "color": row["color"],
                          "number": row["move_number"], "clock_seconds": row["clock_after_seconds"], "elapsed_seconds": row["time_spent_seconds"]})
            positions.append(position(row["fen_after"], [row["uci"][:2], row["uci"][2:4]], next_phase(chess.Board(row["fen_after"]), row["phase_before"])))
        return {"moves": moves, "positions": positions}

    def lesson_games(self, username):
        with self.connection() as db:
            result = []
            for row in self._game_rows(db, username):
                color = "white" if row["white_username"].lower() == username else "black"
                result.append({"id": row["game_id"], "pgn": row["raw_pgn"], "metadata": game_api(row, row["ply_count"]),
                    "analysis_revision": row["analysis_revision"], "pgn_hash": pgn_fingerprint(row["raw_pgn"], row["analysis_revision"]),
                    "moves": {str(m["decision_ply"]): engine_result(m) for m in self._moves(db, row) if m["color"] == color}})
            return result

    def dev_games(self):
        with self.connection() as db:
            return [{k: v for k, v in game_api(row, row["ply_count"]).items() if k != "pgn"} for row in self._game_rows(db)]

    def analysis_reset_runs(self, game_id):
        with self.connection() as db:
            return [r["id"] for r in db.execute("""SELECT id FROM multi_game_analysis WHERE %s::text IS NULL OR input_snapshot @> %s
                OR username IN (SELECT username FROM profile_games WHERE game_id=%s)""",
                (game_id, Jsonb({"mistakes_by_category": [{"mistakes": [{"game": game_id}]}]}), game_id))]

    def _clear_analysis(self, db, ids):
        db.execute("UPDATE games SET analysis_revision=analysis_revision+1,white_accuracy=NULL,black_accuracy=NULL,statistics_version=NULL WHERE game_id=ANY(%s)", (ids,))
        engine = db.execute("DELETE FROM analysis_jobs WHERE game_id=ANY(%s)", (ids,)).rowcount
        feedback = db.execute("SELECT COUNT(*) AS n FROM game_moves WHERE game_id=ANY(%s) AND coach_metadata IS NOT NULL", (ids,)).fetchone()["n"]
        db.execute("DELETE FROM review_attempts WHERE move_id IN (SELECT move_id FROM game_moves WHERE game_id=ANY(%s))", (ids,))
        columns = [r["column_name"] for r in db.execute("""SELECT column_name FROM information_schema.columns
            WHERE table_schema=current_schema() AND table_name='game_moves' AND
            (column_name LIKE 'engine_%' OR column_name LIKE 'played_%' OR column_name LIKE 'top_%'
             OR column_name LIKE 'coach_%' OR column_name IN ('sharpness_score','sharpness_classification','move_quality'))""")]
        update(db, "game_moves", {name: "not_run" if name == "engine_status" else None for name in columns}, "game_id=ANY(%s)", [ids])
        feedback += db.execute("DELETE FROM coach_feedback WHERE game_id=ANY(%s)", (ids,)).rowcount
        reports = db.execute("DELETE FROM multi_game_analysis WHERE username IN (SELECT username FROM profile_games WHERE game_id=ANY(%s))", (ids,)).rowcount
        return engine, feedback, reports

    def reset_analysis(self, game_id):
        with self.connection() as db:
            rows = db.execute("SELECT game_id FROM games WHERE %s::text IS NULL OR game_id=%s ORDER BY game_id FOR UPDATE", (game_id, game_id)).fetchall()
            if game_id is not None and not rows:
                raise ValueError("Game not found.")
            ids = [r["game_id"] for r in rows]
            engine, feedback, reports = self._clear_analysis(db, ids)
            if game_id is None:
                feedback += db.execute("DELETE FROM coach_feedback").rowcount
                reports += db.execute("DELETE FROM multi_game_analysis").rowcount
            return {"game_ids": ids, "games_reset": len(ids), "engine_records": engine, "coach_records": feedback, "reports": reports}

    @staticmethod
    def _moves(db, game):
        return db.execute("SELECT * FROM game_moves WHERE game_id=%s AND engine_status='completed' AND engine_pgn_hash=%s ORDER BY decision_ply",
                          (game["game_id"], game["pgn_hash"])).fetchall()

    @staticmethod
    def _job_summary(db, game, color):
        fingerprint = pgn_fingerprint(game["raw_pgn"], game["analysis_revision"])
        job = db.execute("SELECT * FROM analysis_jobs WHERE game_id=%s AND player_color=%s AND pgn_hash=%s",
                         (game["game_id"], color, fingerprint)).fetchone()
        if job is None:
            return None
        counts = db.execute("""SELECT color,move_quality,COUNT(*) AS n FROM game_moves
            WHERE game_id=%s AND engine_status='completed' AND engine_pgn_hash=%s GROUP BY color,move_quality""",
            (game["game_id"], game["pgn_hash"])).fetchall()
        job["completed"] = sum(r["n"] for r in counts if r["color"] == color)
        job["opponent_completed"] = sum(r["n"] for r in counts if r["color"] != color)
        job["counts"] = {r["move_quality"].lower(): r["n"] for r in counts if r["color"] == color and r["move_quality"]}
        return job

    def _job(self, db, game, color):
        fingerprint = pgn_fingerprint(game["raw_pgn"], game["analysis_revision"])
        job = db.execute("SELECT * FROM analysis_jobs WHERE game_id=%s AND player_color=%s AND pgn_hash=%s", (game["game_id"], color, fingerprint)).fetchone()
        if not job:
            return None
        rows = self._moves(db, game)
        job["moves"] = {str(row["decision_ply"]): engine_result(row) for row in rows if row["color"] == color}
        job["opponent_moves"] = {str(row["decision_ply"]): engine_result(row) for row in rows if row["color"] != color}
        job["completed"] = len(job["moves"])
        job["counts"] = quality_counts(job["moves"])
        final = next((r["engine_final_position"] for r in rows if r["engine_final_position"]), None)
        job["statistics"] = None
        if final:
            final = {k: v for k, v in final.items() if k != "position_evidence"}
            stats = build_statistics(replay(game["raw_pgn"]), {**job["moves"], **job["opponent_moves"]}, final)
            stats["version"] = game["statistics_version"]
            stats["accuracy"] = {"white": game["white_accuracy"], "black": game["black_accuracy"]}
            job["statistics"] = stats
        return job

    def game_analysis(self, game_id, color, fingerprint):
        with self.connection() as db:
            game = db.execute("SELECT * FROM games WHERE game_id=%s", (game_id,)).fetchone()
            return self._job(db, game, color) if game and pgn_fingerprint(game["raw_pgn"], game["analysis_revision"]) == fingerprint else None

    def move_engine(self, game_id, ply):
        with self.connection() as db:
            row = db.execute("""SELECT m.* FROM game_moves m JOIN games g USING(game_id)
                WHERE m.game_id=%s AND decision_ply=%s AND engine_status='completed' AND engine_pgn_hash=g.pgn_hash""", (game_id, ply)).fetchone()
            return engine_result(row) if row else None

    def game_analyses(self, game_id, pgn):
        with self.connection() as db:
            game = db.execute("SELECT * FROM games WHERE game_id=%s AND raw_pgn=%s", (game_id, pgn)).fetchone()
            if not game:
                return {}
            return {color: analysis_result(job) for color in ("white", "black") if (job := self._job(db, game, color)) is not None}

    def interrupt_game_analyses(self):
        with self.connection() as db:
            db.execute("UPDATE analysis_jobs SET status='interrupted',error='Analysis paused when the app restarted. Resume to finish.',updated_at=clock_timestamp() WHERE status IN ('queued','running')")
            db.execute("UPDATE game_moves SET engine_status='failed',engine_error='Search interrupted by restart.' WHERE engine_status='running'")
            for row in db.execute("SELECT * FROM review_attempts WHERE status='in_progress' FOR UPDATE").fetchall():
                entries = row["tried_moves"]
                if any(e["grading_status"] == "pending" for e in entries):
                    for entry in entries:
                        if entry["grading_status"] == "pending":
                            entry["grading_status"] = "failed"
                    update(db, "review_attempts", {"tried_moves": entries}, "review_id=%s", [row["review_id"]])

    def begin_game_analysis(self, game_id, color, fingerprint, total, opponent_total=None):
        with self.connection() as db:
            game = self._current(db, game_id, fingerprint)
            if not game:
                raise ValueError("Game changed before analysis could start.")
            row = self._job(db, game, color)
            if (row and row["status"] == "completed" and row["coach_version"] == COACH_CONTRACT_VERSION
                    and row["coach_completed"] >= coaching_total(row) and (row["statistics"] or {}).get("complete")
                    and (row["statistics"] or {}).get("version") == STATISTICS_VERSION
                    and (opponent_total is None or len(row["opponent_moves"]) == opponent_total)):
                return row
            db.execute("""INSERT INTO analysis_jobs (game_id,player_color,pgn_hash,status,total,opponent_total,coach_version)
                VALUES (%s,%s,%s,'queued',%s,%s,%s) ON CONFLICT(game_id,player_color) DO UPDATE
                SET pgn_hash=excluded.pgn_hash,status='queued',total=excluded.total,opponent_total=excluded.opponent_total,
                    coach_completed=CASE WHEN analysis_jobs.coach_version=excluded.coach_version THEN analysis_jobs.coach_completed ELSE 0 END,
                    coach_version=excluded.coach_version,error=NULL,updated_at=clock_timestamp()""",
                (game_id, color, fingerprint, total, opponent_total, COACH_CONTRACT_VERSION))
            return self._job(db, game, color)

    @staticmethod
    def _current(db, game_id, fingerprint):
        game = db.execute("SELECT * FROM games WHERE game_id=%s FOR UPDATE", (game_id,)).fetchone()
        return game if game and pgn_fingerprint(game["raw_pgn"], game["analysis_revision"]) == fingerprint else None

    def mark_engine_move(self, game_id, fingerprint, ply, status, error=None):
        with self.connection() as db:
            if not self._current(db, game_id, fingerprint):
                return False
            return update(db, "game_moves", {"engine_status": status, "engine_error": error},
                          "game_id=%s AND decision_ply=%s AND engine_status<>'completed'", [game_id, ply]).rowcount > 0

    @staticmethod
    def _save_engine(db, game, move, result, fingerprint):
        fields = engine_columns({**move, "pgn_hash": game["pgn_hash"]}, result, fingerprint)
        fields["engine_analyzed_at"] = datetime.now(timezone.utc)
        update(db, "game_moves", fields, "move_id=%s", [move["move_id"]])
        persisted = db.execute("SELECT * FROM game_moves WHERE move_id=%s", (move["move_id"],)).fetchone()
        update(db, "game_moves", derived_columns(persisted), "move_id=%s", [move["move_id"]])

    def save_game_analysis_move(self, game_id, color, fingerprint, ply, result):
        with self.connection() as db:
            game = self._current(db, game_id, fingerprint)
            if not game:
                return False
            move = db.execute("SELECT * FROM game_moves WHERE game_id=%s AND decision_ply=%s FOR UPDATE", (game_id, ply)).fetchone()
            if not move:
                return False
            self._save_engine(db, game, move, result, fingerprint)
            db.execute("UPDATE analysis_jobs SET updated_at=clock_timestamp() WHERE game_id=%s", (game_id,))
            return True

    save_game_opponent_move = save_game_analysis_move

    def save_game_statistics(self, game_id, color, fingerprint, statistics):
        with self.connection() as db:
            game = self._current(db, game_id, fingerprint)
            if not game:
                return False
            final = dict(statistics["timeline"][-1])
            if final.get("position_evidence"):
                evidence = final["position_evidence"]
                final["position_evidence"] = orient_evidence(evidence, evidence.get("perspective") == "Black")
            last = db.execute("SELECT * FROM game_moves WHERE game_id=%s ORDER BY decision_ply DESC LIMIT 1", (game_id,)).fetchone()
            if not last or final.get("fen") != last["fen_after"] or final.get("ply") != last["decision_ply"]+1:
                raise ValueError("Final evidence does not match this game.")
            update(db, "game_moves", {"engine_final_position": final}, "move_id=%s", [last["move_id"]])
            reviews = {str(m["decision_ply"]): engine_result(m) for m in self._moves(db, game)}
            computed = build_statistics(replay(game["raw_pgn"]), reviews, final)
            update(db, "games", {"white_accuracy": computed["accuracy"]["white"], "black_accuracy": computed["accuracy"]["black"],
                                  "statistics_version": STATISTICS_VERSION}, "game_id=%s", [game_id])
            return True

    def save_game_coach_progress(self, game_id, color, fingerprint, completed):
        with self.connection() as db:
            return db.execute("UPDATE analysis_jobs SET coach_completed=GREATEST(coach_completed,%s),updated_at=clock_timestamp() WHERE game_id=%s AND player_color=%s AND pgn_hash=%s", (completed, game_id, color, fingerprint)).rowcount > 0

    def set_game_analysis_status(self, game_id, color, fingerprint, status, error):
        with self.connection() as db:
            db.execute("UPDATE analysis_jobs SET status=%s,error=%s,updated_at=clock_timestamp() WHERE game_id=%s AND player_color=%s AND pgn_hash=%s", (status, error, game_id, color, fingerprint))
    def multi_game_analyses(self, username: str) -> list[dict]:
        with self.connection() as db:
            return db.execute(f"SELECT {MULTI_GAME_COLUMNS} FROM multi_game_analysis WHERE username=%s ORDER BY created_at DESC, id DESC",
                              (username,)).fetchall()

    def begin_multi_game_analysis(self, run_id: str, username: str, payload: dict, model: str, effort: str) -> dict:
        with self.connection() as db:
            return db.execute(f"""INSERT INTO multi_game_analysis
                              (id, username, status, input_snapshot, model, reasoning_effort)
                              VALUES (%s, %s, 'queued', %s, %s, %s) RETURNING {MULTI_GAME_COLUMNS}""",
                              (run_id, username, Jsonb(payload), model, effort)).fetchone()

    def set_multi_game_status(self, run_id: str, status: str, error: str | None = None):
        with self.connection() as db:
            db.execute("""UPDATE multi_game_analysis SET status=%s, error=%s, updated_at=clock_timestamp()
                       WHERE id=%s AND status IN ('queued', 'running')""", (status, error, run_id))

    def complete_multi_game_analysis(self, run_id: str, result: dict):
        with self.connection() as db:
            db.execute("""UPDATE multi_game_analysis SET status='completed', report=%s, model=%s,
                       response_id=%s, usage=%s, error=NULL, updated_at=clock_timestamp()
                       WHERE id=%s AND status IN ('queued', 'running')""",
                       (Jsonb(result["report"]), result["model"], result["response_id"],
                        Jsonb(result["usage"]) if result.get("usage") is not None else None, run_id))

    def interrupt_multi_game_analyses(self):
        with self.connection() as db:
            db.execute("""UPDATE multi_game_analysis SET status='interrupted',
                       error='Analysis stopped when the app restarted. Run a new analysis to try again.',
                       updated_at=clock_timestamp() WHERE status IN ('queued', 'running')""")


    def cache(self, url: str) -> dict | None:
        with self.connection() as db:
            return db.execute("SELECT * FROM http_cache WHERE url=%s", (url,)).fetchone()

    def save_cache(self, url: str, body: dict, etag: str | None, modified: str | None, now: float):
        with self.connection() as db:
            db.execute("INSERT INTO http_cache (url, body, etag, modified, fetched) VALUES (%s, %s, %s, %s, %s) ON CONFLICT(url) DO UPDATE SET body=excluded.body, etag=excluded.etag, modified=excluded.modified, fetched=excluded.fetched", (url, json.dumps(body), etag, modified, now))

    def save_coach_feedback(self, analysis, *, game_id=None, expected_revision=0, decision_ply=None):
        with self.connection() as db:
            game = None
            if game_id is not None:
                game = db.execute("SELECT * FROM games WHERE game_id=%s FOR UPDATE", (game_id,)).fetchone()
                if game is None or game["analysis_revision"] != expected_revision:
                    return None
            if game is not None and analysis.played_move is not None:
                matches = db.execute("""SELECT * FROM game_moves WHERE game_id=%s AND fen_before=%s AND uci=%s
                    AND (%s::integer IS NULL OR decision_ply=%s) FOR UPDATE""",
                    (game_id, analysis.position.fen, analysis.played_move, decision_ply, decision_ply)).fetchall()
                if len(matches) != 1:
                    raise ValueError("Coaching must identify exactly one recorded move.")
                move = matches[0]
                payload = analysis.position_analysis or {}
                teaching = payload.get("structured") or analysis.structured or {}
                raw = analysis.output_raw or payload.get("output_raw")
                raw_teaching = json.loads(raw) if raw else teaching
                evaluation = raw_teaching.get("move_evaluation") or {}
                category = evaluation.get("mistake_classification") or {}
                # Historical/custom adapters may already have normalized the label.
                original_category = "other" if category.get("category") == "positional" else category.get("category")
                evidence = payload.get("engine_evidence") or analysis.engine_evidence
                fingerprint = pgn_fingerprint(game["raw_pgn"], game["analysis_revision"])
                if move["engine_status"] != "completed" and analysis.stockfish and analysis.stockfish.get("top_moves"):
                    self._save_engine(db, game, move, {"fen": move["fen_before"], "played_move": move["uci"],
                        "stockfish": analysis.stockfish, "position_evidence": evidence}, fingerprint)
                    move = db.execute("SELECT * FROM game_moves WHERE move_id=%s", (move["move_id"],)).fetchone()
                metadata = {"model": analysis.model, "response_id": analysis.response_id, "usage": analysis.usage,
                    "generated_at": datetime.now(timezone.utc).isoformat(), "text": analysis.text,
                    "context_key": context_key(analysis.previous_move), "previous_move": analysis.previous_move,
                    "coach_contract_version": payload.get("coach_contract_version"),
                    "classification_version": payload.get("classification_version"), "sharpness_version": payload.get("sharpness_version"),
                    "normalized_classification": (teaching.get("move_evaluation") or {}).get("mistake_classification"),
                    "engine_evidence_identity": {"pgn_hash": game["pgn_hash"], "revision": expected_revision,
                        "move_id": move["move_id"], "analyzed_at": move["engine_analyzed_at"].isoformat() if move["engine_analyzed_at"] else None},
                    "raw_response_available": raw is not None}
                fields = {"coach_position_overview": teaching.get("position_overview"),
                    "coach_position_explanation": teaching.get("position_explanation"),
                    "coach_candidate_moves": teaching.get("candidate_moves"),
                    "coach_move_explanation": evaluation.get("explanation"),
                    "coach_error_category": original_category,
                    "coach_error_subcategory": category.get("subcategory") if original_category != "other" else None,
                    "coach_decision_context": raw_teaching.get("decision_context"),
                    "coach_output_raw": raw, "coach_metadata": metadata}
                update(db, "game_moves", fields, "move_id=%s", [move["move_id"]])
                return self._coach_row({**move, **fields})
            # Standalone FEN or terminal-board commentary has no recorded move.
            row = insert(db, "coach_feedback", {"fen": analysis.position.fen, "text": analysis.text,
                "model": analysis.model, "response_id": analysis.response_id, "usage": analysis.usage,
                "played_move": analysis.played_move or "", "position_analysis": analysis.position_analysis,
                "move_analysis": analysis.move_analysis, "stockfish": analysis.stockfish,
                "context_key": context_key(analysis.previous_move), "game_id": game_id}, "RETURNING *").fetchone()
            return self._standalone_row(row)

    @staticmethod
    def _standalone_row(row):
        payload = row.get("position_analysis") or {}
        return {"fen": row["fen"], "played_move": row["played_move"] or None,
            **{key: row[key] for key in ("text", "model", "response_id", "created_at", "stockfish")},
            **{key: payload.get(key) for key in ("classification_version", "sharpness_version", "coach_contract_version", "previous_move")},
            "teaching": payload.get("structured"), "position_evidence": payload.get("engine_evidence")}

    @staticmethod
    def _coach_row(row):
        metadata = row["coach_metadata"]
        result = engine_result(row) if row["engine_status"] == "completed" else {}
        teaching = None if row["coach_position_explanation"] is None else {
            "position_overview": row["coach_position_overview"], "position_explanation": row["coach_position_explanation"],
            "candidate_moves": row["coach_candidate_moves"] or [], "decision_context": row["coach_decision_context"],
            "move_evaluation": {"explanation": row["coach_move_explanation"],
                                "mistake_classification": metadata.get("normalized_classification")}}
        return {"fen": row["fen_before"], "played_move": row["uci"], "text": metadata["text"], "model": metadata["model"],
                "response_id": metadata["response_id"], "created_at": datetime.fromisoformat(metadata["generated_at"]),
                "stockfish": result.get("stockfish"), "position_evidence": result.get("position_evidence"), "teaching": teaching,
                **{key: metadata.get(key) for key in ("classification_version", "sharpness_version", "coach_contract_version", "previous_move")}}

    def coach_feedback_for_positions(self, fens):
        return {fen: row for (fen, _), row in self.coach_feedback_for_reviews([(fen, None) for fen in fens]).items()}

    def coach_feedback_for_reviews(self, reviews, *, game_id=None):
        if not reviews:
            return {}
        with self.connection() as db:
            fens = list({r[0] for r in reviews})
            rows = db.execute("""SELECT * FROM coach_feedback WHERE fen=ANY(%s)
                AND (%s::text IS NULL OR game_id=%s) ORDER BY created_at DESC,id DESC""", (fens, game_id, game_id)).fetchall()
            entries = [(r["fen"], r["played_move"] or None, r["context_key"], self._standalone_row(r)) for r in rows]
            if game_id is not None:
                moves = db.execute("SELECT * FROM game_moves WHERE game_id=%s AND fen_before=ANY(%s) AND coach_metadata IS NOT NULL", (game_id, fens)).fetchall()
                entries = [(m["fen_before"], m["uci"], m["coach_metadata"].get("context_key", ""), self._coach_row(m)) for m in moves] + entries
        result = {}
        for original in reviews:
            fen, move = original[:2]
            history = original[2] if len(original) > 2 else ""
            exact = next((row for f, m, h, row in entries if (f, m, h) == (fen, move, history)), None)
            legacy = next((row for f, m, h, row in entries if (f, m, h) == (fen, move, "") and row["coach_contract_version"] is None), None)
            if exact or legacy:
                result[original] = exact or legacy
        return result

    def review_sessions(self, game_id, ply):
        with self.connection() as db:
            return db.execute("""SELECT r.* FROM review_attempts r JOIN game_moves m USING(move_id)
                WHERE m.game_id=%s AND m.decision_ply=%s ORDER BY review_number DESC""", (game_id, ply)).fetchall()

    def game_reviews(self, game_id):
        with self.connection() as db:
            rows = db.execute("""SELECT DISTINCT ON (m.decision_ply) m.decision_ply,r.*
                FROM review_attempts r JOIN game_moves m USING(move_id) WHERE m.game_id=%s
                ORDER BY m.decision_ply,r.review_number DESC""", (game_id,)).fetchall()
            return {str(row.pop("decision_ply")): row for row in rows}

    @staticmethod
    def _review_move(db, game_id, ply, revision):
        game = db.execute("SELECT analysis_revision FROM games WHERE game_id=%s FOR UPDATE", (game_id,)).fetchone()
        if not game or game["analysis_revision"] != revision:
            raise ReviewConflict("This game's analysis changed. Reload the game before reviewing it.")
        move = db.execute("SELECT * FROM game_moves WHERE game_id=%s AND decision_ply=%s FOR UPDATE", (game_id, ply)).fetchone()
        if not move:
            raise ReviewConflict("This recorded move no longer exists.")
        return move

    @staticmethod
    def _start_review(db, move_id, repeat=False):
        latest = db.execute("SELECT * FROM review_attempts WHERE move_id=%s ORDER BY review_number DESC LIMIT 1 FOR UPDATE", (move_id,)).fetchone()
        if latest and (not repeat or latest["status"] == "in_progress"):
            return latest
        return insert(db, "review_attempts", {"move_id": move_id, "review_number": latest["review_number"]+1 if latest else 1}, "RETURNING *").fetchone()

    def start_review(self, game_id, ply, revision, *, repeat=False):
        with self.connection() as db:
            move = self._review_move(db, game_id, ply, revision)
            return self._start_review(db, move["move_id"], repeat)

    def reserve_review_submission(self, game_id, ply, revision, uci, submission_id, review_id=None):
        with self.connection() as db:
            move = self._review_move(db, game_id, ply, revision)
            if chess.Move.from_uci(uci) not in chess.Board(move["fen_before"]).legal_moves:
                raise ReviewConflict("The submitted move is not legal in this position.")
            session = self._start_review(db, move["move_id"])
            if review_id is not None and session["review_id"] != review_id:
                raise ReviewConflict("A different review session is active. Reload practice.")
            previous = next((e for e in session["tried_moves"] if e["submission_id"] == submission_id), None)
            if previous:
                if previous["uci"] != uci:
                    raise ReviewConflict("This submission ID already identifies another move.")
                return session, previous, False
            if session["status"] != "in_progress":
                raise ReviewConflict("This review is complete. Start a new review to try it again.")
            if any(e["grading_status"] == "pending" for e in session["tried_moves"]):
                raise ReviewConflict("A move in this review is still being graded.")
            entry = {"submission_id": submission_id, "uci": uci, "quality": None, "grading_status": "pending"}
            session["tried_moves"] = [*session["tried_moves"], entry]
            update(db, "review_attempts", {"tried_moves": session["tried_moves"]}, "review_id=%s", [session["review_id"]])
            return session, entry, True

    def finish_review_submission(self, game_id, ply, revision, review_id, submission_id, quality=None):
        with self.connection() as db:
            move = self._review_move(db, game_id, ply, revision)
            session = db.execute("SELECT * FROM review_attempts WHERE review_id=%s AND move_id=%s FOR UPDATE", (review_id, move["move_id"])).fetchone()
            if not session:
                raise ReviewConflict("This review was cleared. Reload the game.")
            entry = next((e for e in session["tried_moves"] if e["submission_id"] == submission_id), None)
            if not entry:
                raise ReviewConflict("This submission no longer exists.")
            if entry["grading_status"] == "pending":
                entry.update(quality=quality.title() if quality else None, grading_status="graded" if quality else "failed")
                if quality in ACCEPTABLE_STATUSES:
                    session["status"] = "completed"
                update(db, "review_attempts", {"status": session["status"], "tried_moves": session["tried_moves"]}, "review_id=%s", [review_id])
            return session
