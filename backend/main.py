import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .chess_games import replay
from .coach.routes import AnalyzePositionResponse, create_coach_router
from .coach.preparation_routes import create_preparation_router
from .coach.service import open_coach
from .database import Database
from .importer import ChessComImporter
from .game_analysis import GameAnalysisService, analyze_game_move, create_game_analysis_router
from .migrate_sqlite import migrate_sqlite

ROOT = Path(__file__).resolve().parent.parent


class ImportRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    limit: int = Field(default=50, ge=1, le=100)

    @field_validator("username", mode="before")
    @classmethod
    def clean_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


def create_app(database_url: str | None = None, transport=None, *, coach_factory=open_coach, game_engine=analyze_game_move) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Compose injects these variables; local Python runs read the same file.
        # Explicit process environment values always take precedence.
        load_dotenv(ROOT / ".env", override=False)
        app.state.db = Database(database_url if database_url is not None else os.getenv("DATABASE_URL", ""))
        legacy_path = os.getenv("LEGACY_SQLITE_PATH")
        if legacy_path and database_url is None:
            migrate_sqlite(app.state.db, legacy_path)
        app.state.jobs = {}
        app.state.tasks = set()
        app.state.db.interrupt_game_analyses()
        app.state.game_analysis = GameAnalysisService(app.state.db, app.state.tasks, game_engine)
        async with httpx.AsyncClient(timeout=20, transport=transport, headers={"User-Agent": os.getenv("CHESSCOM_USER_AGENT", "ChessStudy/0.1 (local game library)"), "Accept": "application/json"}) as client:
            app.state.importer = ChessComImporter(app.state.db, client)
            yield
            tasks = list(app.state.tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="Chess Study API", lifespan=lifespan)
    app.include_router(create_coach_router(coach_factory))
    app.include_router(create_preparation_router())
    app.include_router(create_game_analysis_router())

    @app.exception_handler(psycopg.Error)
    async def database_error(request, exc):
        # Connection strings and driver diagnostics can contain credentials.
        return JSONResponse(status_code=503, content={"detail": "The database is unavailable. Please try again shortly."})

    @app.get("/api/health")
    def health():
        app.state.db.health()
        return {"status": "ok"}

    @app.get("/api/profiles")
    def profiles():
        return app.state.db.profiles()

    @app.get("/api/games")
    def games(username: str = Query(min_length=1, max_length=50)):
        return app.state.db.games(username.lower())

    @app.get("/api/games/{game_id}")
    def game(game_id: str):
        record = app.state.db.game(game_id)
        if not record:
            raise HTTPException(404, "Game not found.")
        detail = replay(record["pgn"])
        reviews = [(position["fen"], detail["moves"][ply]["uci"] if ply < len(detail["moves"]) else None)
                   for ply, position in enumerate(detail["positions"])]
        feedback = app.state.db.coach_feedback_for_reviews(reviews + [(fen, None) for fen, _ in reviews])
        # Legacy position-only answers remain visible until a move review exists.
        return {**record, **detail, "engine_analyses": app.state.db.game_analyses(game_id, record["pgn"]), "coach_responses": {
            str(ply): AnalyzePositionResponse(**answer).model_dump(mode="json")
            for ply, (fen, move) in enumerate(reviews)
            if (answer := feedback.get((fen, move)) or feedback.get((fen, None))) is not None
        }}

    @app.get("/api/games/{game_id}/pgn")
    def download(game_id: str):
        record = app.state.db.game(game_id)
        if not record:
            raise HTTPException(404, "Game not found.")
        return Response(record["pgn"], media_type="application/x-chess-pgn", headers={"Content-Disposition": f'attachment; filename="game-{record["id"]}.pgn"'})

    @app.post("/api/imports", status_code=202)
    async def start_import(request: ImportRequest):
        active = next((job for job in app.state.jobs.values() if job["status"] in {"queued", "running"}), None)
        if active:
            if active["username"] == request.username:
                return active
            raise HTTPException(409, "Another import is running. Please wait for it to finish.")
        if len(app.state.jobs) >= 20:
            del app.state.jobs[next(iter(app.state.jobs))]
        job_id = uuid.uuid4().hex
        job = {"id": job_id, "username": request.username, "status": "queued", "found": 0, "added": 0, "skipped": 0, "message": "Starting import…"}
        app.state.jobs[job_id] = job
        task = asyncio.create_task(app.state.importer.run(request.username, request.limit, job))
        app.state.tasks.add(task)
        task.add_done_callback(app.state.tasks.discard)
        return job

    @app.get("/api/imports/{job_id}")
    def import_status(job_id: str):
        if job_id not in app.state.jobs:
            raise HTTPException(404, "This import session expired. You can safely import again.")
        return app.state.jobs[job_id]

    # API routes must precede the frontend mount; missing APIs stay JSON 404s.
    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    def unknown_api(path: str):
        raise HTTPException(404, "API endpoint not found.")

    frontend = Path(os.getenv("FRONTEND_DIST", str(ROOT / "frontend" / "dist")))
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    else:
        @app.get("/")
        def no_frontend():
            return {"message": "API is running. Start the frontend dev server or build frontend/dist.", "docs": "/docs"}
    return app


app = create_app()
