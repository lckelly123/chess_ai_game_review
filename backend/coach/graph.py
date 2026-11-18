"""Single-node coach workflow shared by the application, CLI, and Studio."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from langgraph.channels import EphemeralValue
from langgraph.graph import END, START, StateGraph
from typing_extensions import NotRequired, TypedDict

from .move_review import MoveReview
from .position import CoachPosition
from .responses import CoachAnalysis, ResponsesCoach, open_response_client
from .settings import CoachSettings


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


async def _analyze_from_environment(fen: str, *, played_move: str | None = None) -> CoachAnalysis:
    # Studio can load and inspect the graph without credentials. Validate before
    # creating a client, just as the web endpoint and CLI do.
    position = CoachPosition.from_fen(fen)
    settings = CoachSettings.from_env()
    async with open_response_client(settings) as client:
        return await ResponsesCoach(client, settings).analyze(position.fen, played_move=played_move)


def build_coach_graph(
    analyze: Callable[..., Awaitable[CoachAnalysis]] | None = None,
):
    """Inject an adapter for app/test client reuse; Studio resolves it lazily."""
    analyze = analyze or _analyze_from_environment

    async def analyze_position(state: CoachInput) -> dict:
        position = CoachPosition.from_fen(state["fen"])
        move = state.get("played_move")
        if move is not None:
            move = MoveReview.from_fen(position.fen, move).played_move_uci
        result = await analyze(position.fen, played_move=move)
        return {
            "fen": result.position.fen,
            "ascii_board": result.position.ascii_board,
            "side_to_move": result.position.side_to_move,
            "text": result.text,
            "response_id": result.response_id,
            "model": result.model,
            "usage": result.usage,
            "move_uci": move,
            "position_analysis": result.as_pass(), "move_analysis": None, "stockfish": result.stockfish,
        }

    builder = StateGraph(CoachState, input_schema=CoachInput)
    builder.add_node("analyze_position", analyze_position)
    builder.add_edge(START, "analyze_position")
    # The old evaluate_move adapter remains available, but is not a graph node
    # or reachable edge. Even runs with a recorded move make only one model call.
    builder.add_edge("analyze_position", END)
    # Agent Server supplies persistence in Studio; ordinary coach calls remain
    # independent and do not need a thread ID or an in-process checkpointer.
    return builder.compile(name="chess_coach")


graph = build_coach_graph()
