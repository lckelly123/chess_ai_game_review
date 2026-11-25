"""Engine-only attempts at a recorded decision; never generates coaching."""

import asyncio

import chess
from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from .coach.move_review import MoveReview
from .chess_games import replay
from .coach.context import context_key, previous_move_from_replay
from .coach.move_quality import analyze_played_move
from .coach.position_classification import analyze_position
from .coach.stockfish import StockfishAnalysisError, StockfishTimeoutError, StockfishUnavailableError


class PracticeAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fen: str = Field(min_length=1, max_length=120)
    original_move: str = Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")
    move: str = Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")


def move_option(board: chess.Board, move: chess.Move) -> dict:
    san = board.san(move)
    after = board.copy()
    after.push(move)
    return {"uci": move.uci(), "san": san, "position": {
        "fen": after.fen(),
        "last_move": [chess.square_name(move.from_square), chess.square_name(move.to_square)],
        "check_square": chess.square_name(after.king(after.turn)) if after.is_check() else None,
    }}


def saved_evidence(db, game_id: str, pgn: str, ply: int, original: MoveReview):
    color = original.position.side_to_move.lower()
    analysis = db.game_analyses(game_id, pgn).get(color) or {}
    saved = analysis.get("moves", {}).get(str(ply)) or {}
    if saved.get("fen") == original.position.fen and saved.get("played_move") == original.played_move_uci:
        evidence = saved.get("position_evidence")
        if evidence and evidence.get("fen") == original.position.fen and evidence.get("top_moves"):
            return evidence
    key = (original.position.fen, original.played_move_uci, context_key(previous_move_from_replay(replay(pgn), ply)))
    saved = db.coach_feedback_for_reviews([key]).get(key) or {}
    evidence = saved.get("position_evidence")
    if evidence and evidence.get("fen") == original.position.fen and evidence.get("top_moves"):
        return evidence
    return None


def grade_attempt(review: MoveReview, evidence: dict | None) -> dict:
    # Attempts need only severity. Motif inspection belongs to saved review ingestion.
    return analyze_played_move(review, evidence or analyze_position(review.position.fen), include_tactics=False)


def create_practice_router(analyzer=grade_attempt) -> APIRouter:
    router = APIRouter(prefix="/api/games", tags=["practice"])
    fallback_lock = asyncio.Lock()

    async def context(http_request, game_id, ply):
        record = await run_in_threadpool(http_request.app.state.db.game, game_id)
        if record is None:
            raise HTTPException(404, "Game not found.")
        try:
            original = await run_in_threadpool(MoveReview.from_game, record["pgn"], ply)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return record, original

    @router.get("/{game_id}/practice/{ply}")
    async def practice_position(game_id: str, http_request: Request, ply: int = Path(ge=0)):
        _, original = await context(http_request, game_id, ply)
        board = chess.Board(original.position.fen)
        return {"fen": original.position.fen, "original_move": original.played_move_uci,
                "legal_moves": [move_option(board, move) for move in board.legal_moves]}

    @router.post("/{game_id}/practice/{ply}")
    async def attempt(game_id: str, request: PracticeAttempt, http_request: Request, ply: int = Path(ge=0)):
        record, original = await context(http_request, game_id, ply)
        if request.fen != original.position.fen or request.original_move != original.played_move_uci:
            raise HTTPException(409, "This game position has changed. Reload the game before trying again.")
        try:
            review = MoveReview.from_fen(original.position.fen, request.move)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        service = getattr(http_request.app.state, "game_analysis", None)
        lock = service.engine_lock if service is not None else fallback_lock
        if lock.locked():
            raise HTTPException(409, "Stockfish is analyzing another move. Try again shortly.")
        async with lock:
            evidence = await run_in_threadpool(saved_evidence, http_request.app.state.db, game_id, record["pgn"], ply, original)
            try:
                result = await run_in_threadpool(analyzer, review, evidence)
            except StockfishUnavailableError as exc:
                raise HTTPException(503, "Stockfish is unavailable. Check its installation and try again.") from exc
            except StockfishTimeoutError as exc:
                raise HTTPException(504, "Stockfish took too long. Please try the move again.") from exc
            except StockfishAnalysisError as exc:
                raise HTTPException(502, "Stockfish could not grade this move. Please try again.") from exc
        quality = result["move_quality"]
        return {"fen": original.position.fen, "original_move": original.played_move_uci,
                "move": review.played_move_uci, "quality": quality, "accepted": quality["status"] == "good"}

    return router
