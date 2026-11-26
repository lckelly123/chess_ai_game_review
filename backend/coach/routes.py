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
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from ..chess_games import replay
from .move_review import MoveReview
from .position import CoachPosition, InvalidPositionError
from .service import CoachResponseError, open_coach
from .settings import CoachConfigurationError, CoachModel, CoachSettings, DEFAULT_COACH_MODEL
from .stockfish import StockfishAnalysisError, StockfishTimeoutError, StockfishUnavailableError
from .teaching import TeachingAnalysis
from .lines import move_lines
from .classification import CLASSIFICATION_VERSION
from .player_move_quality import with_player_move_quality, assess_player_move, ERROR_STATUSES
from .sharpness import SHARPNESS_VERSION, with_position_sharpness
from .context import COACH_CONTRACT_VERSION, context_key, previous_move_from_replay


class AnalyzePositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fen: str | None = Field(default=None, min_length=1, max_length=256)
    game_id: str | None = Field(default=None, min_length=1, max_length=64)
    ply: int | None = Field(default=None, ge=0, strict=True)
    model: CoachModel = DEFAULT_COACH_MODEL

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
    stockfish: dict | None = None
    teaching: TeachingAnalysis | None = None
    classification_version: int | None = None
    sharpness_version: int | None = None
    coach_contract_version: int | None = None
    previous_move: dict | None = None

    @computed_field
    @property
    def coach_current(self) -> bool:
        return self.coach_contract_version == COACH_CONTRACT_VERSION

    @computed_field
    @property
    def better_candidate_uci(self) -> str | None:
        """UI comparison is an engine decision, outside the LLM output."""
        if self.teaching is None or self.stockfish is None:
            return None
        played = self.stockfish.get("played_move") or {}
        if self.stockfish.get("move_quality", {}).get("status") not in ERROR_STATUSES:
            return None
        candidates = {move["uci"]: move for move in (self.position_evidence or {}).get("top_moves", [])}
        for candidate in self.teaching.candidate_moves:
            if assess_player_move(candidates.get(candidate.uci, {}), played)["status"] in ERROR_STATUSES:
                return candidate.uci
        return None

    @computed_field
    @property
    def sharpness_current(self) -> bool:
        return self.sharpness_version == SHARPNESS_VERSION

    @model_validator(mode="after")
    def refresh_position_sharpness(self):
        if self.position_evidence is not None:
            self.position_evidence = with_position_sharpness(self.position_evidence, expected_fen=self.fen)
        return self

    @computed_field
    @property
    def classification_current(self) -> bool:
        return self.classification_version == CLASSIFICATION_VERSION
    position_evidence: dict | None = None

    @field_validator("stockfish")
    @classmethod
    def current_player_quality(cls, evidence):
        return with_player_move_quality(evidence) if evidence is not None else None

    @computed_field
    @property
    def candidate_san(self) -> dict[str, str]:
        return self.teaching.candidate_san(self.fen) if self.teaching is not None else {}

    @computed_field
    @property
    def move_lines(self) -> dict:
        allowed = set(self.candidate_san)
        if self.played_move:
            allowed.add(self.played_move)
        stockfish = self.stockfish or {}
        moves = {move["uci"]: move for move in stockfish.get("top_moves", []) if move.get("uci") in allowed}
        moves.update({move["uci"]: move for move in (self.position_evidence or {}).get("top_moves", [])
                      if move.get("uci") in allowed})
        played = stockfish.get("played_move") or {}
        if played.get("uci") == self.played_move and self.played_move:
            moves[self.played_move] = played
        return move_lines(self.fen, moves)


def create_coach_router(coach_factory=open_coach, *, request_lock=None) -> APIRouter:
    router = APIRouter(prefix="/api/coach", tags=["coach"])
    # This is a single-user, single-worker app. Reject overlapping requests
    # rather than queueing extra paid generations (including other tabs).
    request_lock = request_lock if request_lock is not None else asyncio.Lock()

    @router.get("/feedback", response_model=AnalyzePositionResponse | None)
    async def saved_feedback(http_request: Request, fen: str = Query(min_length=1, max_length=256),
                             played_move: str | None = Query(default=None, min_length=4, max_length=5),
                             game_id: str | None = None, ply: int | None = Query(default=None, ge=0)):
        try:
            position = CoachPosition.from_fen(fen)
            if played_move is not None:
                played_move = MoveReview.from_fen(position.fen, played_move).played_move_uci
            previous_move = None
            if (game_id is None) != (ply is None):
                raise InvalidPositionError("Supply game_id and ply together for game context.")
            if game_id is not None:
                record = await run_in_threadpool(http_request.app.state.db.game, game_id)
                if record is None:
                    raise HTTPException(404, "Game not found.")
                detail = await run_in_threadpool(replay, record["pgn"])
                if ply >= len(detail["positions"]) or detail["positions"][ply]["fen"] != position.fen:
                    raise InvalidPositionError("Game context does not match the selected position.")
                previous_move = previous_move_from_replay(detail, ply)
        except InvalidPositionError as exc:
            raise HTTPException(422, str(exc)) from exc
        key = (position.fen, played_move, context_key(previous_move))
        saved = await run_in_threadpool(http_request.app.state.db.coach_feedback_for_reviews, [key], game_id=game_id)
        return saved.get(key)

    @router.post("/analyze", response_model=AnalyzePositionResponse)
    async def analyze_position(request: AnalyzePositionRequest, http_request: Request):
        database = http_request.app.state.db
        played_move = None
        previous_move = None
        try:
            if request.game_id is not None:
                record = await run_in_threadpool(database.game, request.game_id)
                if record is None:
                    raise HTTPException(404, "Game not found.")
                detail = await run_in_threadpool(replay, record["pgn"])
                if request.ply >= len(detail["positions"]):
                    raise InvalidPositionError("The selected replay position is outside this game.")
                position = CoachPosition.from_fen(detail["positions"][request.ply]["fen"])
                previous_move = previous_move_from_replay(detail, request.ply)
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
                async with coach_factory(CoachSettings.from_env(model=request.model)) as coach:
                    result = await coach.analyze(position.fen,
                                                 **({"played_move": played_move} if played_move is not None else {}),
                                                 **({"previous_move": previous_move} if previous_move else {}))
                if result.position.fen != position.fen or result.played_move != played_move:
                    raise CoachResponseError("The coach returned a different position.", result.response_id)
                try:
                    scope = {"game_id": request.game_id, "expected_revision": record.get("analysis_revision", 0)} if request.game_id else {}
                    saved = await run_in_threadpool(database.save_coach_feedback, result, **scope)
                    if saved is None:
                        raise HTTPException(409, "Analysis was cleared while this review was running. Run it again for fresh results.")
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
                raise HTTPException(502, f"The configured OpenAI project cannot access {request.model}. Check model access for this API key.") from exc
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
