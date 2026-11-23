"""Durable run history with one explicit background generation per player."""

import asyncio
import logging
from uuid import uuid4

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from openai import (APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError,
                    BadRequestError, NotFoundError, PermissionDeniedError, RateLimitError)
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from ..coach.responses import CoachResponseError
from ..coach.settings import CoachConfigurationError
from ..lessons import multi_game_input
from .graph import MODEL, REASONING_EFFORT, build_multi_game_graph
from .output import MultiGameReport

logger = logging.getLogger(__name__)
ACTIVE = {"queued", "running"}


def failure_message(exc: Exception) -> str:
    if isinstance(exc, (CoachConfigurationError, AuthenticationError)):
        return "Coach configuration is missing or invalid. Check the API key and settings, then run again."
    if isinstance(exc, (PermissionDeniedError, NotFoundError)):
        return f"The configured OpenAI project cannot access {MODEL}. Check model access, then run again."
    if isinstance(exc, RateLimitError):
        return "OpenAI's rate limit or usage quota was reached. Check your API usage, then run again."
    if isinstance(exc, APITimeoutError):
        return "The coach took too long to respond. No automatic retry was made. You can run a new analysis."
    if isinstance(exc, APIConnectionError):
        return "Could not connect to OpenAI. Check the connection, then run again."
    if isinstance(exc, BadRequestError):
        if exc.code in {"context_length_exceeded", "input_too_long"}:
            return "The saved mistakes exceed the model's input limit. No mistakes were silently removed; a smaller analysis scope is needed."
        return "OpenAI rejected the analysis request. Check model settings and the input size before running again."
    if isinstance(exc, CoachResponseError):
        return "The coach did not return a complete, valid report. You can run a new analysis."
    if isinstance(exc, psycopg.Error):
        return "The analysis could not be saved because the database became unavailable. Previous responses are kept."
    if isinstance(exc, APIStatusError):
        return "OpenAI could not complete this analysis. You can run a new analysis."
    return "Analysis could not finish. Previous responses are kept. You can run a new analysis."


class MultiGameService:
    def __init__(self, database, tasks: set, analyzer=None):
        self.db, self.tasks = database, tasks
        self.graph = build_multi_game_graph(analyzer)
        self.start_lock = asyncio.Lock()
        self.active = {}

    async def _saved(self, username):
        rows = await run_in_threadpool(self.db.multi_game_analyses, username)
        for row in rows:
            task = self.active.get(row["id"])
            if row["status"] in ACTIVE and (task is None or task.done()):
                # The worker may have completed between reading its row and task.
                # The database update only touches still-active runs.
                await run_in_threadpool(self.db.set_multi_game_status, row["id"], "interrupted",
                                       "Analysis stopped before a report was saved. Run a new analysis to try again.")
        return await run_in_threadpool(self.db.multi_game_analyses, username)

    async def saved(self, username):
        async with self.start_lock:
            return await self._saved(username.lower())

    async def start(self, username):
        async with self.start_lock:
            previous = await self._saved(username)
            if any(row["status"] in ACTIVE for row in previous):
                raise HTTPException(409, "Multi-game analysis is already running for this player.")
            payload = await run_in_threadpool(multi_game_input, self.db, username)
            if not payload["summary"]["errors"]["total"]:
                raise HTTPException(422, "Analyze a game with recorded mistakes before running multi-game analysis.")
            run_id = str(uuid4())
            try:
                row = await run_in_threadpool(self.db.begin_multi_game_analysis, run_id, username, payload, MODEL, REASONING_EFFORT)
            except psycopg.errors.UniqueViolation as exc:
                raise HTTPException(409, "Multi-game analysis is already running for this player.") from exc
            task = asyncio.create_task(self._run(run_id, payload))
            self.active[run_id] = task
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            task.add_done_callback(lambda _: self.active.pop(run_id, None))
            return row

    async def _run(self, run_id, payload):
        try:
            await run_in_threadpool(self.db.set_multi_game_status, run_id, "running")
            result = await self.graph.ainvoke(payload)
            # Validate even injected adapters before writing a completed result.
            result["report"] = MultiGameReport.model_validate(result["report"]).model_dump()
            await run_in_threadpool(self.db.complete_multi_game_analysis, run_id, result)
        except asyncio.CancelledError:
            try:
                await run_in_threadpool(self.db.set_multi_game_status, run_id, "interrupted",
                                       "Analysis stopped when the app shut down. Run a new analysis to try again.")
            except Exception:
                logger.warning("Could not persist interrupted multi-game analysis.")
            raise
        except Exception as exc:
            logger.warning("Multi-game analysis stopped (%s).", type(exc).__name__)
            try:
                await run_in_threadpool(self.db.set_multi_game_status, run_id, "failed", failure_message(exc))
            except Exception:
                logger.warning("Could not persist multi-game analysis failure status.")


class StartMultiGameAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


def create_multi_game_router():
    router = APIRouter(prefix="/api/lessons/multi-game", tags=["multi-game coach"])

    @router.get("")
    async def history(request: Request, username: str = Query(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")):
        return await request.app.state.multi_game.saved(username)

    @router.post("", status_code=202)
    async def start(body: StartMultiGameAnalysis, request: Request):
        return await request.app.state.multi_game.start(body.username)

    return router
