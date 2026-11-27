"""Resumable engine analysis of both sides and coaching of one player's errors."""

import asyncio
from collections import Counter
import hashlib
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from .chess_games import parse_game, replay
from .game_statistics import STATISTICS_VERSION, build_statistics, position_evaluation, terminal_evaluation
from .coach.context import COACH_CONTRACT_VERSION, current_coaching, context_key, previous_move_from_replay
from .coach.move_review import MoveReview
from .coach.lines import candidate_positions
from .coach.move_quality import analyze_played_move
from .coach.player_move_quality import with_player_move_quality
from .coach.position_classification import analyze_position
from .coach.sharpness import with_position_sharpness
from .coach.stockfish import StockfishAnalysisError, StockfishTimeoutError, StockfishUnavailableError
from .coach.service import CoachResponseError, open_coach
from .coach.settings import CoachConfigurationError, CoachModel, CoachSettings, DEFAULT_COACH_MODEL

logger = logging.getLogger(__name__)
ACTIVE_STATUSES = {"queued", "running"}
COACH_QUALITIES = {"inaccuracy", "mistake", "blunder"}


def coaching_total(row: dict) -> int:
    return sum(row["counts"].get(quality, 0) for quality in COACH_QUALITIES)


def pgn_fingerprint(pgn: str, revision: int = 0) -> str:
    source = pgn if not revision else f"{pgn}\nanalysis-reset:{revision}"
    return hashlib.sha256(source.encode()).hexdigest()


def player_color(record: dict, username: str) -> str:
    for color in ("white", "black"):
        if record[color].lower() == username.strip().lower():
            return color
    raise ValueError("Choose a player who took part in this game.")


def analysis_summary(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {**{key: row[key] for key in ("game_id", "player_color", "status", "total", "completed", "counts", "error", "updated_at")},
            "opponent_total": row.get("opponent_total"),
            "opponent_completed": row.get("opponent_completed", len(row.get("opponent_moves", {}))),
            "coach_total": coaching_total(row),
            "coach_completed": row.get("coach_completed", 0) if row.get("coach_version") == COACH_CONTRACT_VERSION else 0}


def analysis_result(row: dict | None) -> dict | None:
    if row is None:
        return None
    def rescored(moves):
        return {ply: {**move, "candidate_positions": candidate_positions(move["fen"],
            [item["uci"] for item in move["stockfish"].get("top_moves", [])[:3]]),
            "position_evidence": with_position_sharpness(
            move.get("position_evidence") or {**move["stockfish"], "fen": move["fen"]}, expected_fen=move["fen"])}
                for ply, move in moves.items()}
    return {**analysis_summary(row), "moves": rescored(row["moves"]),
            "opponent_moves": rescored(row.get("opponent_moves", {})), "statistics": row.get("statistics")}


def quality_counts(moves: dict) -> dict:
    return dict(Counter(value["stockfish"]["move_quality"]["status"] for value in moves.values()))


def analyze_game_move(review: MoveReview) -> dict:
    # Use the same common-depth position search and played-root comparison as
    # coaching, without constructing a graph or contacting a model. The UI shows
    # the first three of these ranked lines, independent of candidate approval.
    position = analyze_position(review.position.fen)
    result = analyze_played_move(review, position)
    return {"position_evidence": position, **result}


def analyze_final_position(pgn: str) -> dict:
    game = parse_game(pgn)
    board = game.end().board()  # Preserve history for repetition/automatic draw rules.
    ply = sum(1 for _ in game.mainline_moves())
    terminal = terminal_evaluation(board, ply, claim_draw=game.headers.get("Result") == "1/2-1/2")
    if terminal is not None:
        return terminal
    evidence = analyze_position(board.fen())
    point = position_evaluation(evidence, ply, board.fen())
    if point is None:
        raise StockfishAnalysisError("The final position has no reliable evaluation.")
    return {**point, "position_evidence": evidence}


class GameAnalysisService:
    def __init__(self, database, tasks: set, analyzer=analyze_game_move, *, coach_factory=None, coach_lock=None, final_analyzer=None):
        self.db = database
        self.tasks = tasks
        self.analyzer = analyzer
        self.final_analyzer = final_analyzer or analyze_final_position
        self.active = {}
        self.start_lock = asyncio.Lock()
        self.engine_lock = asyncio.Lock()
        self.coach_factory = coach_factory or open_coach
        self.coach_lock = coach_lock if coach_lock is not None else asyncio.Lock()

    async def game_for_player(self, game_id: str, username: str):
        record = await run_in_threadpool(self.db.game, game_id)
        if record is None:
            raise HTTPException(404, "Game not found.")
        try:
            color = player_color(record, username)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return record, color, pgn_fingerprint(record["pgn"], record.get("analysis_revision", 0))

    async def start(self, game_id: str, username: str, model: CoachModel = DEFAULT_COACH_MODEL):
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
            opponents = [(ply, detail["positions"][ply]["fen"], move["uci"])
                         for ply, move in enumerate(detail["moves"]) if move["color"] != color]
            row = await run_in_threadpool(self.db.begin_game_analysis, game_id, color, fingerprint, len(targets), len(opponents))
            if (row["status"] == "completed" and row.get("coach_completed", 0) >= coaching_total(row)
                    and row.get("coach_version") == COACH_CONTRACT_VERSION
                    and (row.get("statistics") or {}).get("complete")
                    and (row.get("statistics") or {}).get("version") == STATISTICS_VERSION):
                return analysis_result(row)
            task = asyncio.create_task(self._run(game_id, color, fingerprint, targets, row["moves"], model,
                                                 opponents, row.get("opponent_moves", {}), detail, record["pgn"], row.get("statistics")))
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
                # The worker may have finished after the first snapshot was read.
                # Recheck its durable status before overwriting a completed job.
                row = await run_in_threadpool(self.db.game_analysis, game_id, color, fingerprint)
                if row and row["status"] in ACTIVE_STATUSES:
                    message = "Analysis paused. Resume to finish the remaining moves."
                    await run_in_threadpool(self.db.set_game_analysis_status, game_id, color, fingerprint, "interrupted", message)
                    row.update(status="interrupted", error=message)
            return analysis_result(row)

    async def _coach_moves(self, game_id, color, fingerprint, targets, saved, model):
        completed = 0
        for ply, fen, uci in targets:
            evidence = saved[str(ply)]
            if evidence["stockfish"].get("move_quality", {}).get("status") not in COACH_QUALITIES:
                continue
            # Share the manual Run coach lock, and check the cache inside it so
            # a manual review finishing while we wait cannot create a duplicate.
            async with self.coach_lock:
                current = await run_in_threadpool(self.db.game, game_id)
                if current is None or pgn_fingerprint(current["pgn"], current.get("analysis_revision", 0)) != fingerprint:
                    return False
                detail = await run_in_threadpool(replay, current["pgn"])
                previous_move = previous_move_from_replay(detail, ply)
                key = (fen, uci, context_key(previous_move))
                previous = await run_in_threadpool(self.db.coach_feedback_for_reviews, [key], game_id=game_id)
                if not current_coaching(previous.get(key)):
                    await run_in_threadpool(self.db.health)
                    options = {}
                    if (evidence.get("position_evidence") and with_position_sharpness(
                            evidence["position_evidence"], expected_fen=fen)["unclassified_reason"] != "insufficient_engine_evidence"):
                        # New jobs reuse the exact evidence that selected this
                        # move. Older engine-only saves use the normal coach search.
                        options = {"position_engine": lambda _: evidence["position_evidence"],
                                   "engine": lambda *_: evidence["stockfish"]}
                    async with self.coach_factory(CoachSettings.from_env(model=model), **options) as coach:
                        result = await coach.analyze(fen, played_move=uci,
                                                     **({"previous_move": previous_move} if previous_move else {}))
                    if result.position.fen != fen or result.played_move != uci:
                        raise CoachResponseError("The coach returned a different position or move.", result.response_id)
                    persisted = await run_in_threadpool(self.db.save_coach_feedback, result, game_id=game_id,
                                                        expected_revision=current.get("analysis_revision", 0))
                    if persisted is None:
                        return False
                completed += 1
                if not await run_in_threadpool(self.db.save_game_coach_progress, game_id, color, fingerprint, completed):
                    return False
        return True

    async def _run(self, game_id, color, fingerprint, targets, saved, model, opponents, saved_opponents, detail, pgn, statistics):
        async def status(value, error=None):
            await run_in_threadpool(self.db.set_game_analysis_status, game_id, color, fingerprint, value, error)
        phase = "engine"
        try:
            # One game search at a time avoids multiplying Stockfish CPU/hash
            # usage when multiple games are submitted. Queued work is durable.
            async with self.engine_lock:
                await status("running")
                other = await run_in_threadpool(self.db.game_analysis, game_id,
                                               "black" if color == "white" else "white", fingerprint)
                reusable = {**(other or {}).get("moves", {}), **(other or {}).get("opponent_moves", {})}
                player_plies = {ply for ply, _, _ in targets}
                for ply, fen, uci in targets + opponents:
                    destination = saved if ply in player_plies else saved_opponents
                    save = self.db.save_game_analysis_move if ply in player_plies else self.db.save_game_opponent_move
                    existing = destination.get(str(ply))
                    if (existing and existing["fen"] == fen and existing["played_move"] == uci
                            and position_evaluation(existing["stockfish"], ply, fen)):
                        continue
                    cached = reusable.get(str(ply))
                    if (cached and cached["fen"] == fen and cached["played_move"] == uci
                            and position_evaluation(cached["stockfish"], ply, fen)):
                        if not await run_in_threadpool(save, game_id, color, fingerprint, ply, cached):
                            return
                        destination[str(ply)] = cached
                        continue
                    review = MoveReview.from_fen(fen, uci)
                    evidence = await run_in_threadpool(self.analyzer, review)
                    if (evidence.get("fen") != review.position.fen
                            or evidence.get("perspective") != review.position.side_to_move
                            or evidence.get("played_move", {}).get("uci") != uci
                            or not evidence.get("top_moves")):
                        raise StockfishAnalysisError("Engine evidence does not match the requested move.")
                    result = {"fen": review.position.fen, "played_move": uci,
                              "stockfish": with_player_move_quality({key: value for key, value in evidence.items()
                                                                     if key != "position_evidence"})}
                    if evidence.get("position_evidence"):
                        result["position_evidence"] = evidence["position_evidence"]
                    persisted = await run_in_threadpool(save, game_id, color, fingerprint, ply, result)
                    if not persisted:
                        return  # The PGN was replaced; never write stale results.
                    destination[str(ply)] = result
                cached_stats = statistics or (other or {}).get("statistics") or {}
                timeline = cached_stats.get("timeline") or []
                final = timeline[-1] if timeline and timeline[-1].get("fen") == detail["positions"][-1]["fen"] else None
                if not final or final.get("status") not in ("evaluated", "terminal"):
                    final = await run_in_threadpool(self.final_analyzer, pgn)
                if final.get("fen") != detail["positions"][-1]["fen"] or final.get("ply") != len(detail["moves"]):
                    raise StockfishAnalysisError("The final evaluation does not match this game.")
                statistics = build_statistics(detail, {**saved, **saved_opponents}, final)
                if not statistics["complete"]:
                    raise StockfishAnalysisError("The evaluation timeline is incomplete.")
                if not await run_in_threadpool(self.db.save_game_statistics, game_id, color, fingerprint, statistics):
                    return
            phase = "coach"
            if await self._coach_moves(game_id, color, fingerprint, targets, saved, model):
                await status("completed")
        except asyncio.CancelledError:
            await status("interrupted", "Analysis paused. Resume to finish the remaining moves.")
            raise
        except Exception as exc:
            if isinstance(exc, CoachConfigurationError):
                message = "Coach configuration is missing or invalid. Check the API key and settings, then resume."
            elif phase == "coach":
                message = "Coaching could not finish. Engine results and saved reviews are kept; resume to try again."
            elif isinstance(exc, StockfishUnavailableError):
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
    model: CoachModel = DEFAULT_COACH_MODEL

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


def create_game_analysis_router() -> APIRouter:
    router = APIRouter(prefix="/api/games", tags=["engine analysis"])

    @router.post("/{game_id}/analysis", status_code=202)
    async def start(game_id: str, body: StartGameAnalysis, request: Request):
        return await request.app.state.game_analysis.start(game_id, body.username, body.model)

    @router.get("/{game_id}/analysis")
    async def saved(game_id: str, request: Request, username: str = Query(min_length=1, max_length=50)):
        return await request.app.state.game_analysis.saved(game_id, username)

    return router
