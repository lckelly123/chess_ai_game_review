"""Public coach interface backed by the shared LangGraph workflow."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from langchain_core.runnables import RunnableConfig
from openai import AsyncOpenAI

from .graph import CoachInput, build_coach_graph
from .position import CoachPosition
from .responses import (
    SYSTEM_PROMPT_PATH, CoachAnalysis, CoachResponseError, ResponsesCoach,
    build_request, open_response_client,
)
from .settings import CoachSettings


class Coach:
    """Reuse an injected SDK client; the caller owns its lifecycle."""

    def __init__(self, client: AsyncOpenAI, settings: CoachSettings | None = None, *, engine=None):
        adapter = ResponsesCoach(client, settings)
        self.client = adapter.client
        self.settings = adapter.settings
        self.graph = build_coach_graph(adapter.analyze, adapter.evaluate_move, engine)

    async def analyze(
        self, fen: str, *, ascii_board: str | None = None, played_move: str | None = None,
        config: RunnableConfig | None = None,
    ) -> CoachAnalysis:
        position = CoachPosition.from_fen(fen, ascii_board=ascii_board)
        state: CoachInput = {"fen": position.fen, "played_move": played_move}
        result = await self.graph.ainvoke(state, config=config)
        return CoachAnalysis(
            text=result["text"], response_id=result["response_id"], model=result["model"],
            position=CoachPosition(result["fen"], result["ascii_board"], result["side_to_move"]),
            usage=result["usage"],
            played_move=result["move_uci"], position_analysis=result["position_analysis"],
            move_analysis=result["move_analysis"], stockfish=result["stockfish"],
        )


@asynccontextmanager
async def open_coach(settings: CoachSettings | None = None) -> AsyncIterator[Coach]:
    settings = settings or CoachSettings.from_env()
    async with open_response_client(settings) as client:
        yield Coach(client, settings)
