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
from .move_quality import analyze_played_move, prepare_position_evidence
from .settings import CoachSettings, require_api_key
from .stockfish import StockfishAnalysisError
from .teaching import TeachingOutput
from .classification import CLASSIFICATION_VERSION
from .sharpness import SHARPNESS_VERSION
from .context import COACH_CONTRACT_VERSION, validate_previous_move

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
    previous_move: dict[str, str] | None = None
    output_raw: str | None = None

    def as_pass(self) -> dict[str, Any]:
        result = {"text": self.text, "response_id": self.response_id, "model": self.model, "usage": self.usage}
        if self.output_raw is not None:
            result["output_raw"] = self.output_raw
        if self.structured is not None:
            result["coach_contract_version"] = COACH_CONTRACT_VERSION
            result["previous_move"] = self.previous_move
            result["structured"] = self.structured
            result["classification_version"] = CLASSIFICATION_VERSION
            result["sharpness_version"] = SHARPNESS_VERSION
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


def _evaluation(move: dict) -> str:
    score = move.get("score") or {}
    mate, cp = score.get("mate"), score.get("cp")
    if mate is not None:
        value = f"mate in {mate}" if mate > 0 else f"mated in {abs(mate)}"
    else:
        value = f"{cp} cp" if cp is not None else "unavailable"
    bound = score.get("bound")
    return f"{value} ({bound} bound)" if bound in ("lower", "upper") else value


def _request_for(position: CoachPosition, settings: CoachSettings, evidence: dict,
                 move_evidence: dict | None = None, previous_move: dict | None = None) -> dict[str, Any]:
    if evidence.get("fen") != position.fen or evidence.get("perspective") != position.side_to_move:
        raise StockfishAnalysisError("Stockfish evidence did not match the selected position.")
    previous_move = validate_previous_move(position.fen, previous_move)
    previous = f"{previous_move['san']} ({previous_move['uci']})" if previous_move else "unavailable"
    mode = evidence["decision_classification"] or f"unclassified ({evidence['unclassified_reason']})"
    permitted = set(evidence["permitted_candidate_uci"])
    lines = [f"{move['uci']} | {_evaluation(move)} | {' '.join(move.get('pv_san') or []) or 'unavailable'}"
             for move in evidence["top_moves"] if move["uci"] in permitted]
    candidates = "\n".join(lines) if lines else "none"
    player = "PLAYER MOVE: none"
    if move_evidence is not None:
        move = move_evidence["played_move"]
        player = (f"PLAYER MOVE\nUCI: {move['uci']}\nSAN: {move['san']}\n"
                  f"Evaluation: {_evaluation(move)}\nSeverity: {move_evidence['move_quality']['status']}\n"
                  f"PV: {' '.join(move.get('pv_san') or []) or 'unavailable'}")
    message = (f"Side to move: {position.side_to_move}\n\nOpponent's previous move: {previous}\n\n"
               f"FEN: {position.fen}\n\n{position.ascii_board}\n\nDecision mode: {mode}\n\n"
               f"APPROVED ENGINE MOVES (ranked best to worst)\nUCI | Evaluation | PV (SAN)\n{candidates}\n\n{player}")
    return {
        **_base_request(settings),
        "text": {"format": {
            "type": "json_schema", "name": "position_teaching", "strict": True,
            "schema": TeachingOutput.model_json_schema(),
        }},
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")},
            {"role": "user", "content": message},
        ],
    }


def build_request(
    fen: str, *, ascii_board: str | None = None, settings: CoachSettings | None = None,
    evidence: dict | None = None,
    played_move: str | None = None, previous_move: dict | None = None,
) -> dict[str, Any]:
    """Preview the exact request using local Stockfish, without any model call."""
    position = CoachPosition.from_fen(fen, ascii_board=ascii_board)
    previous_move = validate_previous_move(position.fen, previous_move)
    review = MoveReview.from_fen(position.fen, played_move) if played_move is not None else None
    evidence = prepare_position_evidence(evidence if evidence is not None else analyze_position(position.fen))
    move_evidence = analyze_played_move(review, evidence) if review else None
    if move_evidence and "position_evidence" in move_evidence:
        move_evidence = dict(move_evidence)
        evidence = move_evidence.pop("position_evidence")
    return _request_for(position, settings or CoachSettings(), evidence, move_evidence, previous_move)


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

    def __init__(self, client: AsyncOpenAI, settings: CoachSettings | None = None, *, position_engine=None, engine=None, on_evidence=None):
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
        self.move_engine = engine or analyze_played_move
        self.on_evidence = on_evidence

    async def analyze(self, fen: str, *, ascii_board: str | None = None, played_move: str | None = None,
                      previous_move: dict | None = None) -> CoachAnalysis:
        position = CoachPosition.from_fen(fen, ascii_board=ascii_board)
        previous_move = validate_previous_move(position.fen, previous_move)
        review = MoveReview.from_fen(position.fen, played_move) if played_move is not None else None
        evidence = prepare_position_evidence(await asyncio.to_thread(self.position_engine, position.fen))
        if evidence.get("fen") != position.fen or evidence.get("perspective") != position.side_to_move:
            raise StockfishAnalysisError("Stockfish evidence did not match the selected position.")
        move_evidence = await asyncio.to_thread(self.move_engine, review, evidence) if review else None
        if review and (move_evidence.get("fen") != position.fen or move_evidence.get("perspective") != position.side_to_move
                       or move_evidence.get("played_move", {}).get("uci") != review.played_move_uci):
            raise StockfishAnalysisError("Engine evidence did not match the reviewed move.")
        if move_evidence and "position_evidence" in move_evidence:
            move_evidence = dict(move_evidence)
            evidence = move_evidence.pop("position_evidence")
        if self.on_evidence is not None:
            await asyncio.to_thread(self.on_evidence, evidence, move_evidence)
        # Prompt reads must not block Agent Server's event loop in Studio.
        request = await asyncio.to_thread(_request_for, position, self.settings, evidence, move_evidence, previous_move)
        return await self._complete(request, position, evidence=evidence, move_evidence=move_evidence, previous_move=previous_move)

    async def evaluate_move(self, review: MoveReview, previous_analysis: dict | str, evidence: dict) -> CoachAnalysis:
        request = await asyncio.to_thread(build_move_request, review, previous_analysis, evidence, self.settings)
        return await self._complete(request, review.position)

    async def _complete(self, request: dict, position: CoachPosition, *, evidence: dict | None = None,
                        move_evidence: dict | None = None, previous_move: dict | None = None) -> CoachAnalysis:
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
                teaching.validate_references(played_move=move_evidence["played_move"]["uci"] if move_evidence else None)
                teaching.validate_move_evaluation(played_move=move_evidence["played_move"]["uci"] if move_evidence else None,
                                                  evidence=move_evidence)
                teaching = teaching.as_analysis(position.fen,
                    played_move=move_evidence["played_move"]["uci"] if move_evidence else None, evidence=evidence)
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
            previous_move=previous_move,
            stockfish=move_evidence,
            played_move=move_evidence["played_move"]["uci"] if move_evidence else None,
            output_raw=response.output_text,
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
