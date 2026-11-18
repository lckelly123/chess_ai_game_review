"""OpenAI Responses API adapter, deliberately independent of the web app."""

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

from openai import AsyncOpenAI
from langsmith.run_helpers import is_traceable_function
from langsmith.wrappers import wrap_openai

from .position import CoachPosition
from .position_classification import analyze_position
from .move_review import MoveReview
from .settings import CoachSettings, require_api_key
from .stockfish import StockfishAnalysisError
from .teaching import TeachingOutput

SYSTEM_PROMPT_PATH = Path(__file__).with_name("system_prompt.md")
MOVE_PROMPT_PATH = Path(__file__).with_name("move_prompt.md")


class CoachResponseError(RuntimeError):
    """A request returned no complete, usable coaching answer."""

    def __init__(self, message: str, response_id: str):
        super().__init__(message)
        self.response_id = response_id


@dataclass(frozen=True)
class CoachAnalysis:
    text: str
    response_id: str
    model: str
    position: CoachPosition
    usage: dict[str, Any] | None
    played_move: str | None = None
    position_analysis: dict[str, Any] | None = None
    move_analysis: dict[str, Any] | None = None
    stockfish: dict[str, Any] | None = None
    structured: dict[str, Any] | None = None
    engine_evidence: dict[str, Any] | None = None

    def as_pass(self) -> dict[str, Any]:
        result = {"text": self.text, "response_id": self.response_id, "model": self.model, "usage": self.usage}
        if self.structured is not None:
            result["structured"] = self.structured
        if self.engine_evidence is not None:
            result["engine_evidence"] = self.engine_evidence
        return result


def _base_request(settings: CoachSettings) -> dict[str, Any]:
    return {
        "model": settings.model,
        "reasoning": {"effort": settings.reasoning_effort},
        "max_output_tokens": settings.max_output_tokens,
        "store": False,
    }


def _request_for(position: CoachPosition, settings: CoachSettings, evidence: dict) -> dict[str, Any]:
    if evidence.get("fen") != position.fen or evidence.get("perspective") != position.side_to_move:
        raise StockfishAnalysisError("Stockfish evidence did not match the selected position.")
    payload = {
        "decision_classification": evidence["decision_classification"],
        "unclassified_reason": evidence["unclassified_reason"],
        "position_outlook": evidence["position_outlook"],
        "engine_verified_moves": evidence["top_moves"],
        "permitted_candidate_uci": evidence["permitted_candidate_uci"],
        "delta_cp": evidence["delta_cp"], "delta_e_pp": evidence["delta_e_pp"],
    }
    return {
        **_base_request(settings),
        "text": {"format": {
            "type": "json_schema", "name": "position_teaching", "strict": True,
            "schema": TeachingOutput.model_json_schema(),
        }},
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")},
            {"role": "user", "content": position.as_user_message() + (
                "\n\nStockfish position evidence:\n" + json.dumps(payload, ensure_ascii=False)
                + "\n\nScores and WDL are from the side to move. Relative losses are compared with the best move; "
                "expected-score gaps are percentage points. All supplied moves are eligible for consideration, "
                "but only recommend sound choices supported by their evaluations. Do not invent a decision classification "
                "when it is null: use the stated reason. For terminal_position, return an empty candidate_moves array "
                "and explain that play has ended. For single_legal_move, recommend the sole verified move."
            )},
        ],
    }


def build_request(
    fen: str, *, ascii_board: str | None = None, settings: CoachSettings | None = None,
    evidence: dict | None = None,
) -> dict[str, Any]:
    """Preview the exact request using local Stockfish, without any model call."""
    position = CoachPosition.from_fen(fen, ascii_board=ascii_board)
    return _request_for(position, settings or CoachSettings(), evidence if evidence is not None else analyze_position(position.fen))


def build_move_request(review: MoveReview, previous_analysis: dict | str, evidence: dict, settings: CoachSettings) -> dict:
    request = _base_request(settings)  # The second pass retains its Markdown move review.
    payload = {**review.as_dict(), "previous_analysis": previous_analysis, "stockfish": evidence}
    request["input"] = [
        {"role": "system", "content": MOVE_PROMPT_PATH.read_text(encoding="utf-8")},
        {"role": "user", "content": (
            "Evaluate the recorded move from this pre-move position using the supplied previous analysis and engine evidence. "
            "Scores are from the side-to-move player's perspective: positive favors that player. "
            "cp is centipawns; mate is signed moves to mate, not centipawns. "
            "Respect score bounds and actual search depths; small differences need not imply mistakes.\n\n"
            + json.dumps(payload, ensure_ascii=False)
        )},
    ]
    return request


class ResponsesCoach:
    """Reuse an injected SDK client; the caller owns its lifecycle."""

    def __init__(self, client: AsyncOpenAI, settings: CoachSettings | None = None, *, position_engine=None):
        # The wrapper mutates the client. An injected client may already be traced.
        if not (
            getattr(client.responses.create, "_coach_traced", False)
            or is_traceable_function(client.responses.create)
        ):
            wrap_openai(client, chat_name="OpenAI Responses")
            client.responses.create._coach_traced = True
        self.client = client
        self.settings = settings or CoachSettings()
        self.position_engine = position_engine or analyze_position

    async def analyze(self, fen: str, *, ascii_board: str | None = None) -> CoachAnalysis:
        position = CoachPosition.from_fen(fen, ascii_board=ascii_board)
        evidence = await asyncio.to_thread(self.position_engine, position.fen)
        # Prompt reads must not block Agent Server's event loop in Studio.
        request = await asyncio.to_thread(_request_for, position, self.settings, evidence)
        return await self._complete(request, position, evidence=evidence)

    async def evaluate_move(self, review: MoveReview, previous_analysis: dict | str, evidence: dict) -> CoachAnalysis:
        request = await asyncio.to_thread(build_move_request, review, previous_analysis, evidence, self.settings)
        return await self._complete(request, review.position)

    async def _complete(self, request: dict, position: CoachPosition, *, evidence: dict | None = None) -> CoachAnalysis:
        response = await self.client.responses.create(**request)
        if response.status != "completed":
            reason = response.incomplete_details.reason if response.incomplete_details else response.status
            raise CoachResponseError(f"Coaching did not complete ({reason}). No partial answer was accepted.", response.id)
        if any(
            part.type == "refusal"
            for item in response.output if item.type == "message"
            for part in item.content
        ):
            raise CoachResponseError("The model declined to provide coaching for this request.", response.id)
        if not response.output_text.strip():
            raise CoachResponseError("The model returned an empty coaching answer.", response.id)
        teaching = None
        if "text" in request:
            try:
                teaching = TeachingOutput.model_validate_json(response.output_text).validate_position(
                    position.fen, permitted_moves=evidence["permitted_candidate_uci"])
            except ValueError as exc:
                raise CoachResponseError("The model returned invalid position teaching or candidate moves.", response.id) from exc
        return CoachAnalysis(
            text=teaching.as_markdown(position.fen) if teaching is not None else response.output_text,
            response_id=response.id,
            model=response.model,
            position=position,
            usage=response.usage.model_dump() if response.usage else None,
            structured=teaching.model_dump() if teaching is not None else None,
            engine_evidence=evidence,
        )


@asynccontextmanager
async def open_response_client(settings: CoachSettings) -> AsyncIterator[AsyncOpenAI]:
    """Create and close a real OpenAI client only when explicitly invoked."""
    async with AsyncOpenAI(
        api_key=require_api_key(),
        base_url="https://api.openai.com/v1",
        timeout=settings.timeout_seconds,
        # A retry could create another paid generation after an ambiguous timeout.
        max_retries=0,
    ) as client:
        yield client
