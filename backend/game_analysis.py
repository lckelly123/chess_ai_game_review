"""Resumable, engine-only analysis of one player's decisions in a saved game."""

import asyncio
from collections import Counter
import hashlib
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from .chess_games import replay
from .coach.move_review import MoveReview
from .coach.move_quality import analyze_played_move
from .coach.player_move_quality import with_player_move_quality
from .coach.position_classification import analyze_position
from .coach.stockfish import StockfishAnalysisError, StockfishTimeoutError, StockfishUnavailableError

logger = logging.getLogger(__name__)
ACTIVE_STATUSES = {"queued", "running"}


def pgn_fingerprint(pgn: str) -> str:
    return hashlib.sha256(pgn.encode()).hexdigest()


def player_color(record: dict, username: str) -> str:
    for color in ("white", "black"):
        if record[color].lower() == username.strip().lower():
            return color
    raise ValueError("Choose a player who took part in this game.")


def analysis_summary(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {key: row[key] for key in ("game_id", "player_color", "status", "total", "completed", "counts", "error", "updated_at")}


def analysis_result(row: dict | None) -> dict | None:
    return {**analysis_summary(row), "moves": row["moves"]} if row else None


def quality_counts(moves: dict) -> dict:
    return dict(Counter(value["stockfish"]["move_quality"]["status"] for value in moves.values()))


def analyze_game_move(review: MoveReview) -> dict:
    # Use the same common-depth position search and played-root comparison as
    # coaching, without constructing a graph or contacting a model. The UI shows
    # the first three of these ranked lines, independent of candidate approval.
    position = analyze_position(review.position.fen)
    return analyze_played_move(review, position)


class GameAnalysisService:
    def __init__(self, database, tasks: set, analyzer=analyze_game_move):
        self.db = database
        self.tasks = tasks
        self.analyzer = analyzer
        self.active = {}
        self.start_lock = asyncio.Lock()
        self.engine_lock = asyncio.Lock()

    async def game_for_player(self, game_id: str, username: str):
        record = await run_in_threadpool(self.db.game, game_id)
        if record is None:
            raise HTTPException(404, "Game not found.")
        try:
            color = player_color(record, username)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return record, color, pgn_fingerprint(record["pgn"])

    async def start(self, game_id: str, username: str):
        async with self.start_lock:
            record, color, fingerprint = await self.game_for_player(game_id, username)
            key = (game_id, color)
            if key in self.active:
                row = await run_in_threadpool(self.db.game_analysis, game_id, color, fingerprint)
                if row is None:
                    raise HTTPException(409, "An older version of this game is still being analyzed. Try again shortly.")
                return analysis_result(row)
            try:
                detail = await run_in_threadpool(replay, record["pgn"])
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            targets = [(ply, detail["positions"][ply]["fen"], move["uci"])
                       for ply, move in enumerate(detail["moves"]) if move["color"] == color]
            row = await run_in_threadpool(self.db.begin_game_analysis, game_id, color, fingerprint, len(targets))
            if row["status"] == "completed":
                return analysis_result(row)
            task = asyncio.create_task(self._run(game_id, color, fingerprint, targets, row["moves"]))
            self.active[key] = task
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            task.add_done_callback(lambda finished: self.active.pop(key, None))
            return analysis_result(row)

    async def saved(self, game_id: str, username: str):
        _, color, fingerprint = await self.game_for_player(game_id, username)
        async with self.start_lock:
            row = await run_in_threadpool(self.db.game_analysis, game_id, color, fingerprint)
            task = self.active.get((game_id, color))
            # A database outage can prevent a worker from saving its failure status.
            # Recover that case when polling resumes, rather than showing Running forever.
            # The start lock prevents mistaking a just-created job for an orphan.
            if row and row["status"] in ACTIVE_STATUSES and (task is None or task.done()):
                message = "Analysis paused. Resume to finish the remaining moves."
                await run_in_threadpool(self.db.set_game_analysis_status, game_id, color, fingerprint, "interrupted", message)
                row.update(status="interrupted", error=message)
            return analysis_result(row)

    async def _run(self, game_id, color, fingerprint, targets, saved):
        async def status(value, error=None):
            await run_in_threadpool(self.db.set_game_analysis_status, game_id, color, fingerprint, value, error)
        try:
            # One game search at a time avoids multiplying Stockfish CPU/hash
            # usage when multiple games are submitted. Queued work is durable.
            async with self.engine_lock:
                await status("running")
                for ply, fen, uci in targets:
                    existing = saved.get(str(ply))
                    if existing and existing["fen"] == fen and existing["played_move"] == uci:
                        continue
                    review = MoveReview.from_fen(fen, uci)
                    evidence = await run_in_threadpool(self.analyzer, review)
                    if (evidence.get("fen") != review.position.fen
                            or evidence.get("perspective") != review.position.side_to_move
                            or evidence.get("played_move", {}).get("uci") != uci
                            or not evidence.get("top_moves")):
                        raise StockfishAnalysisError("Engine evidence does not match the requested move.")
                    result = {"fen": review.position.fen, "played_move": uci,
                              "stockfish": with_player_move_quality(evidence)}
                    persisted = await run_in_threadpool(self.db.save_game_analysis_move, game_id, color, fingerprint, ply, result)
                    if not persisted:
                        return  # The PGN was replaced; never write stale results.
                await status("completed")
        except asyncio.CancelledError:
            await status("interrupted", "Analysis paused. Resume to finish the remaining moves.")
            raise
        except Exception as exc:
            if isinstance(exc, StockfishUnavailableError):
                message = "Stockfish is unavailable. Check its installation, then resume analysis."
            elif isinstance(exc, StockfishTimeoutError):
                message = "Stockfish took too long. Resume to retry the remaining moves."
            elif isinstance(exc, StockfishAnalysisError):
                message = "Stockfish could not analyze a move. Resume to try again."
            else:
                message = "Analysis could not finish. Saved moves are kept; resume to try again."
            # Do not expose process diagnostics or connection strings to the UI.
            logger.warning("Game analysis stopped (%s).", type(exc).__name__)
            try:
                await status("failed", message)
            except Exception:
                logger.warning("Could not persist game-analysis failure status.")


class StartGameAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


def create_game_analysis_router() -> APIRouter:
    router = APIRouter(prefix="/api/games", tags=["engine analysis"])

    @router.post("/{game_id}/analysis", status_code=202)
    async def start(game_id: str, body: StartGameAnalysis, request: Request):
        return await request.app.state.game_analysis.start(game_id, body.username)

    @router.get("/{game_id}/analysis")
    async def saved(game_id: str, request: Request, username: str = Query(min_length=1, max_length=50)):
        return await request.app.state.game_analysis.saved(game_id, username)

    return router
