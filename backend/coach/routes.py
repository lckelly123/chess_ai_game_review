"""HTTP entry point for position coaching and recorded-move reviews."""

import asyncio
from datetime import datetime

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from openai import (
    APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError,
    NotFoundError, PermissionDeniedError, RateLimitError,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..chess_games import replay
from .move_review import MoveReview
from .position import CoachPosition, InvalidPositionError
from .service import CoachResponseError, open_coach
from .settings import CoachConfigurationError
from .stockfish import StockfishAnalysisError, StockfishTimeoutError, StockfishUnavailableError


class AnalyzePositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fen: str | None = Field(default=None, min_length=1, max_length=256)
    game_id: str | None = Field(default=None, min_length=1, max_length=64)
    ply: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def input_mode(self):
        if self.fen is not None and self.game_id is None and self.ply is None:
            return self
        if self.fen is None and self.game_id is not None and self.ply is not None:
            return self
        raise ValueError("Supply either fen, or game_id and ply together.")


class AnalyzePositionResponse(BaseModel):
    fen: str
    played_move: str | None = None
    text: str
    model: str
    response_id: str
    created_at: datetime


def create_coach_router(coach_factory=open_coach) -> APIRouter:
    router = APIRouter(prefix="/api/coach", tags=["coach"])
    # This is a single-user, single-worker app. Reject overlapping requests
    # rather than queueing extra paid generations (including other tabs).
    request_lock = asyncio.Lock()

    @router.get("/feedback", response_model=AnalyzePositionResponse | None)
    async def saved_feedback(http_request: Request, fen: str = Query(min_length=1, max_length=256),
                             played_move: str | None = Query(default=None, min_length=4, max_length=5)):
        try:
            position = CoachPosition.from_fen(fen)
            if played_move is not None:
                played_move = MoveReview.from_fen(position.fen, played_move).played_move_uci
        except InvalidPositionError as exc:
            raise HTTPException(422, str(exc)) from exc
        saved = await run_in_threadpool(http_request.app.state.db.coach_feedback_for_reviews, [(position.fen, played_move)])
        return saved.get((position.fen, played_move))

    @router.post("/analyze", response_model=AnalyzePositionResponse)
    async def analyze_position(request: AnalyzePositionRequest, http_request: Request):
        database = http_request.app.state.db
        played_move = None
        try:
            if request.game_id is not None:
                record = await run_in_threadpool(database.game, request.game_id)
                if record is None:
                    raise HTTPException(404, "Game not found.")
                detail = await run_in_threadpool(replay, record["pgn"])
                if request.ply >= len(detail["positions"]):
                    raise InvalidPositionError("The selected replay position is outside this game.")
                position = CoachPosition.from_fen(detail["positions"][request.ply]["fen"])
                if request.ply < len(detail["moves"]):
                    played_move = MoveReview.from_fen(position.fen, detail["moves"][request.ply]["uci"]).played_move_uci
            else:
                position = CoachPosition.from_fen(request.fen)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if request_lock.locked():
            raise HTTPException(409, "The coach is already reviewing a position. Wait for it to finish, then try again.")
        async with request_lock:
            # Avoid starting a paid request when persistence is already down.
            await run_in_threadpool(database.health)
            try:
                async with coach_factory() as coach:
                    result = await coach.analyze(position.fen, played_move=played_move) if played_move is not None else await coach.analyze(position.fen)
                if result.position.fen != position.fen or result.played_move != played_move:
                    raise CoachResponseError("The coach returned a different position.", result.response_id)
                try:
                    saved = await run_in_threadpool(database.save_coach_feedback, result)
                except psycopg.Error as exc:
                    raise HTTPException(503, "The coach replied, but its feedback could not be saved. Any previously saved answer is unchanged.") from exc
                return AnalyzePositionResponse(**saved)
            except CoachConfigurationError as exc:
                raise HTTPException(503, "Coach configuration is missing or invalid. Check OPENAI_API_KEY and coach settings in .env, then restart the app.") from exc
            except StockfishUnavailableError as exc:
                raise HTTPException(503, "Stockfish is unavailable. Check its installation and settings, then restart the app.") from exc
            except StockfishTimeoutError as exc:
                raise HTTPException(504, "Stockfish took too long. The move review was not saved; please try again.") from exc
            except StockfishAnalysisError as exc:
                raise HTTPException(502, "Stockfish could not complete the move review. Please try again.") from exc
            except AuthenticationError as exc:
                raise HTTPException(503, "OpenAI rejected the configured API key. Check OPENAI_API_KEY in .env, then restart the app.") from exc
            except (PermissionDeniedError, NotFoundError) as exc:
                raise HTTPException(502, "The configured OpenAI project cannot access GPT-6 Astra. Check model access for this API key.") from exc
            except RateLimitError as exc:
                raise HTTPException(429, "OpenAI's rate limit or usage quota was reached. Check your API usage, then try again.") from exc
            except APITimeoutError as exc:
                raise HTTPException(504, "The coach took too long to respond. You can try again; no automatic retry was made.") from exc
            except APIConnectionError as exc:
                raise HTTPException(502, "Could not connect to OpenAI. Check the connection and try again.") from exc
            except CoachResponseError as exc:
                raise HTTPException(502, "The coach did not return a complete answer. Please try again.") from exc
            except APIStatusError as exc:
                raise HTTPException(502, "OpenAI could not complete this request. Please try again.") from exc

    return router
