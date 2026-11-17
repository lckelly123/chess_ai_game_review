"""Prepare engine-backed move inputs independently of paid coaching."""

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from .move_review import MoveReview
from .stockfish import analyze_move, StockfishAnalysisError, StockfishTimeoutError, StockfishUnavailableError


class PrepareMoveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game_id: str = Field(min_length=1, max_length=64)
    ply: int = Field(ge=0, strict=True)


def create_preparation_router(analyzer=analyze_move) -> APIRouter:
    router = APIRouter(prefix="/api/coach", tags=["coach"])
    engine_lock = asyncio.Lock()

    @router.post("/prepare-move")
    async def prepare_move(request: PrepareMoveRequest, http_request: Request):
        if engine_lock.locked():
            raise HTTPException(409, "Stockfish is already analyzing a move. Wait for it to finish.")
        async with engine_lock:
            record = await run_in_threadpool(http_request.app.state.db.game, request.game_id)
            if record is None:
                raise HTTPException(404, "Game not found.")
            try:
                review = await run_in_threadpool(MoveReview.from_game, record["pgn"], request.ply)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            try:
                evidence = await run_in_threadpool(analyzer, review)
            except StockfishUnavailableError as exc:
                raise HTTPException(503, "Stockfish is unavailable. Check its installation and STOCKFISH settings, then restart the app.") from exc
            except StockfishTimeoutError as exc:
                raise HTTPException(504, "Stockfish took too long to respond. Please try again.") from exc
            except StockfishAnalysisError as exc:
                raise HTTPException(502, "Stockfish could not complete the move analysis. Please try again.") from exc
            return {"game_id": request.game_id, "ply": request.ply, **review.as_dict(), "stockfish": evidence}

    return router
