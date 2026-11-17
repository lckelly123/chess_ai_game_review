"""Two-pass coach workflow shared by the application, CLI, and Studio."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from langgraph.channels import EphemeralValue
from langgraph.graph import END, START, StateGraph
from typing_extensions import NotRequired, TypedDict

from .move_review import MoveReview
from .position import CoachPosition
from .responses import CoachAnalysis, ResponsesCoach, open_response_client
from .settings import CoachSettings
from .stockfish import analyze_move, StockfishAnalysisError


class CoachInput(TypedDict):
    fen: str
    # Only this invocation's move, never a previous Studio run's input.
    played_move: NotRequired[Annotated[str | None, EphemeralValue(str | None)]]


class CoachState(CoachInput):
    """JSON-compatible channels that subsequent nodes can read and extend."""

    fen: str
    ascii_board: str
    side_to_move: str
    move_uci: str | None
    text: str
    response_id: str
    model: str
    usage: dict[str, Any] | None
    position_analysis: dict[str, Any]
    move_analysis: dict[str, Any] | None
    stockfish: dict[str, Any] | None


async def _analyze_from_environment(fen: str) -> CoachAnalysis:
    # Studio can load and inspect the graph without credentials. Validate before
    # creating a client, just as the web endpoint and CLI do.
    position = CoachPosition.from_fen(fen)
    settings = CoachSettings.from_env()
    async with open_response_client(settings) as client:
        return await ResponsesCoach(client, settings).analyze(position.fen)


async def _evaluate_from_environment(review: MoveReview, previous: dict | str, evidence: dict) -> CoachAnalysis:
    settings = CoachSettings.from_env()
    async with open_response_client(settings) as client:
        return await ResponsesCoach(client, settings).evaluate_move(review, previous, evidence)


def _sum_usage(first: dict | None, second: dict | None) -> dict | None:
    if first is None or second is None:
        return None  # Do not report a partial total as the complete run's usage.
    combined = {}
    for key in first.keys() | second.keys():
        left, right = first.get(key, 0), second.get(key, 0)
        if isinstance(left, dict) or isinstance(right, dict):
            combined[key] = _sum_usage(left if isinstance(left, dict) else {}, right if isinstance(right, dict) else {})
        elif isinstance(left, (int, float)) and isinstance(right, (int, float)):
            combined[key] = left + right
    return combined


def build_coach_graph(
    analyze: Callable[[str], Awaitable[CoachAnalysis]] | None = None,
    evaluate: Callable[[MoveReview, dict | str, dict], Awaitable[CoachAnalysis]] | None = None,
    engine: Callable[[MoveReview], dict] | None = None,
):
    """Inject an adapter for app/test client reuse; Studio resolves it lazily."""
    analyze = analyze or _analyze_from_environment
    evaluate = evaluate or _evaluate_from_environment
    engine = engine or analyze_move

    async def analyze_position(state: CoachInput) -> dict:
        position = CoachPosition.from_fen(state["fen"])
        move = state.get("played_move")
        if move is not None:
            move = MoveReview.from_fen(position.fen, move).played_move_uci
        # First pass sees neither the played move nor engine evidence.
        result = await analyze(position.fen)
        return {
            "fen": result.position.fen,
            "ascii_board": result.position.ascii_board,
            "side_to_move": result.position.side_to_move,
            "text": result.text,
            "response_id": result.response_id,
            "model": result.model,
            "usage": result.usage,
            "move_uci": move,
            "position_analysis": result.as_pass(), "move_analysis": None, "stockfish": None,
        }

    async def evaluate_move(state: CoachState) -> dict:
        review = MoveReview.from_fen(state["fen"], state["move_uci"])
        evidence = await asyncio.to_thread(engine, review)
        if (evidence.get("perspective") != review.position.side_to_move
                or evidence.get("played_move", {}).get("uci") != review.played_move_uci):
            raise StockfishAnalysisError("Engine evidence did not match the reviewed move.")
        first = state["position_analysis"]
        result = await evaluate(review, first.get("structured", first["text"]), evidence)
        return {
            "text": first["text"] + "\n\n" + result.text,
            "response_id": result.response_id, "model": result.model,
            "usage": _sum_usage(first["usage"], result.usage),
            "move_analysis": result.as_pass(), "stockfish": evidence,
        }

    builder = StateGraph(CoachState, input_schema=CoachInput)
    builder.add_node("analyze_position", analyze_position)
    builder.add_node("evaluate_move", evaluate_move)
    builder.add_edge(START, "analyze_position")
    builder.add_conditional_edges("analyze_position", lambda state: "move" if state["move_uci"] is not None else "done",
                                  {"move": "evaluate_move", "done": END})
    builder.add_edge("evaluate_move", END)
    # Agent Server supplies persistence in Studio; ordinary coach calls remain
    # independent and do not need a thread ID or an in-process checkpointer.
    return builder.compile(name="chess_coach")


graph = build_coach_graph()
