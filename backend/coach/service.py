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

    def __init__(self, client: AsyncOpenAI, settings: CoachSettings | None = None, *, engine=None, position_engine=None, on_evidence=None):
        adapter = ResponsesCoach(client, settings, position_engine=position_engine, engine=engine, on_evidence=on_evidence)
        self.client = adapter.client
        self.settings = adapter.settings
        self.graph = build_coach_graph(adapter.analyze)

    async def analyze(
        self, fen: str, *, ascii_board: str | None = None, played_move: str | None = None,
        previous_move: dict | None = None,
        config: RunnableConfig | None = None,
    ) -> CoachAnalysis:
        position = CoachPosition.from_fen(fen, ascii_board=ascii_board)
        state: CoachInput = {"fen": position.fen, "played_move": played_move, "previous_move": previous_move}
        result = await self.graph.ainvoke(state, config=config)
        return CoachAnalysis(
            text=result["text"], response_id=result["response_id"], model=result["model"],
            position=CoachPosition(result["fen"], result["ascii_board"], result["side_to_move"]),
            usage=result["usage"],
            played_move=result["move_uci"], position_analysis=result["position_analysis"],
            move_analysis=result["move_analysis"], stockfish=result["stockfish"],
            previous_move=result["previous_move_context"],
            output_raw=result["position_analysis"].get("output_raw"),
        )


@asynccontextmanager
async def open_coach(settings: CoachSettings | None = None, *, position_engine=None, engine=None, on_evidence=None) -> AsyncIterator[Coach]:
    settings = settings or CoachSettings.from_env()
    async with open_response_client(settings) as client:
        yield Coach(client, settings, position_engine=position_engine, engine=engine, on_evidence=on_evidence)
