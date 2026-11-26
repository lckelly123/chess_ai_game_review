"""Explicit reset controls for the local, single-user development app."""

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool


class ResetAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game_id: str | None = Field(default=None, min_length=1, max_length=64)


def create_dev_router(coach_lock: asyncio.Lock) -> APIRouter:
    router = APIRouter(prefix="/api/dev", tags=["development"])

    @router.get("/games")
    async def games(request: Request):
        return await run_in_threadpool(request.app.state.db.dev_games)

    async def reset(state, game_id):
        games, reports = state.game_analysis, state.multi_game
        # No fresh job can start between cancellation and the durable reset.
        async with games.start_lock, reports.start_lock:
            if game_id is not None and await run_in_threadpool(state.db.game, game_id) is None:
                raise HTTPException(404, "Game not found.")
            run_ids = await run_in_threadpool(state.db.analysis_reset_runs, game_id)
            pending = [task for (target, _), task in games.active.items() if game_id is None or target == game_id]
            pending += [reports.active[run_id] for run_id in run_ids if run_id in reports.active]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            # Manual coaching shares this lock. Any request already in progress
            # finishes before deletion; guarded game writes reject old revisions.
            async with coach_lock:
                return await run_in_threadpool(state.db.reset_analysis, game_id)

    @router.post("/analysis/reset")
    async def reset_analysis(body: ResetAnalysisRequest, request: Request):
        task = asyncio.create_task(reset(request.app.state, body.game_id))
        request.app.state.tasks.add(task)
        task.add_done_callback(request.app.state.tasks.discard)
        # Navigating away must not leave a half-finished cancellation/reset.
        return await asyncio.shield(task)

    return router
