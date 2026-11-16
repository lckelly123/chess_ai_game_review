"""The coach workflow shared by the application, CLI, and LangSmith Studio."""

from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from .position import CoachPosition
from .responses import CoachAnalysis, ResponsesCoach, open_response_client
from .settings import CoachSettings


class CoachInput(TypedDict):
    fen: str


class CoachState(TypedDict):
    """JSON-compatible channels that subsequent nodes can read and extend."""

    fen: str
    ascii_board: str
    side_to_move: str
    text: str
    response_id: str
    model: str
    usage: dict[str, Any] | None


async def _analyze_from_environment(fen: str) -> CoachAnalysis:
    # Studio can load and inspect the graph without credentials. Validate before
    # creating a client, just as the web endpoint and CLI do.
    position = CoachPosition.from_fen(fen)
    settings = CoachSettings.from_env()
    async with open_response_client(settings) as client:
        return await ResponsesCoach(client, settings).analyze(position.fen)


def build_coach_graph(analyze: Callable[[str], Awaitable[CoachAnalysis]] | None = None):
    """Inject an adapter for app/test client reuse; Studio resolves it lazily."""
    analyze = analyze or _analyze_from_environment

    async def analyze_position(state: CoachInput) -> CoachState:
        # Only the new FEN is input. Derived board/output channels can still be
        # present from an earlier Studio thread run and must never become input.
        result = await analyze(state["fen"])
        return {
            "fen": result.position.fen,
            "ascii_board": result.position.ascii_board,
            "side_to_move": result.position.side_to_move,
            "text": result.text,
            "response_id": result.response_id,
            "model": result.model,
            "usage": result.usage,
        }

    builder = StateGraph(CoachState, input_schema=CoachInput)
    builder.add_node("analyze_position", analyze_position)
    builder.add_edge(START, "analyze_position")
    # Add subsequent nodes and replace this terminal edge as the workflow grows.
    builder.add_edge("analyze_position", END)
    # Agent Server supplies persistence in Studio; ordinary coach calls remain
    # independent and do not need a thread ID or an in-process checkpointer.
    return builder.compile(name="chess_coach")


graph = build_coach_graph()
