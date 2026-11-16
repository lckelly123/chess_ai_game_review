"""HTTP entry point for explicit, position-only coaching requests."""

import asyncio
from datetime import datetime

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from openai import (
    APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError,
    NotFoundError, PermissionDeniedError, RateLimitError,
)
from pydantic import BaseModel, ConfigDict, Field

from .position import CoachPosition, InvalidPositionError
from .service import CoachResponseError, open_coach
from .settings import CoachConfigurationError


class AnalyzePositionRequest(BaseModel):
    # Student questions and game history are deliberately not accepted.
    model_config = ConfigDict(extra="forbid")
    fen: str = Field(min_length=1, max_length=256)


class AnalyzePositionResponse(BaseModel):
    fen: str
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
    async def saved_feedback(http_request: Request, fen: str = Query(min_length=1, max_length=256)):
        try:
            position = CoachPosition.from_fen(fen)
        except InvalidPositionError as exc:
            raise HTTPException(422, str(exc)) from exc
        saved = await run_in_threadpool(http_request.app.state.db.coach_feedback_for_positions, [position.fen])
        return saved.get(position.fen)

    @router.post("/analyze", response_model=AnalyzePositionResponse)
    async def analyze_position(request: AnalyzePositionRequest, http_request: Request):
        try:
            position = CoachPosition.from_fen(request.fen)
        except InvalidPositionError as exc:
            raise HTTPException(422, str(exc)) from exc
        if request_lock.locked():
            raise HTTPException(409, "The coach is already reviewing a position. Wait for it to finish, then try again.")
        async with request_lock:
            database = http_request.app.state.db
            # Avoid starting a paid request when persistence is already down.
            await run_in_threadpool(database.health)
            try:
                async with coach_factory() as coach:
                    result = await coach.analyze(position.fen)
                if result.position.fen != position.fen:
                    raise CoachResponseError("The coach returned a different position.", result.response_id)
                try:
                    saved = await run_in_threadpool(database.save_coach_feedback, result)
                except psycopg.Error as exc:
                    raise HTTPException(503, "The coach replied, but its feedback could not be saved. Any previously saved answer is unchanged.") from exc
                return AnalyzePositionResponse(**saved)
            except CoachConfigurationError as exc:
                raise HTTPException(503, "Coach configuration is missing or invalid. Check OPENAI_API_KEY and coach settings in .env, then restart the app.") from exc
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
