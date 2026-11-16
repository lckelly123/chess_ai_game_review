"""OpenAI Responses API adapter, deliberately independent of the web app."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

from openai import AsyncOpenAI
from langsmith.run_helpers import is_traceable_function
from langsmith.wrappers import wrap_openai

from .position import CoachPosition
from .settings import CoachSettings, require_api_key

SYSTEM_PROMPT_PATH = Path(__file__).with_name("system_prompt.md")


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


def _request_for(position: CoachPosition, settings: CoachSettings) -> dict[str, Any]:
    return {
        "model": settings.model,
        "reasoning": {"effort": settings.reasoning_effort},
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")},
            {"role": "user", "content": position.as_user_message()},
        ],
        "max_output_tokens": settings.max_output_tokens,
        "store": False,
    }


def build_request(
    fen: str, *, ascii_board: str | None = None, settings: CoachSettings | None = None,
) -> dict[str, Any]:
    """Preview the exact request without credentials or a network call."""
    position = CoachPosition.from_fen(fen, ascii_board=ascii_board)
    return _request_for(position, settings or CoachSettings())


class ResponsesCoach:
    """Reuse an injected SDK client; the caller owns its lifecycle."""

    def __init__(self, client: AsyncOpenAI, settings: CoachSettings | None = None):
        # The wrapper mutates the client. An injected client may already be traced.
        if not (
            getattr(client.responses.create, "_coach_traced", False)
            or is_traceable_function(client.responses.create)
        ):
            wrap_openai(client, chat_name="OpenAI Responses")
            client.responses.create._coach_traced = True
        self.client = client
        self.settings = settings or CoachSettings()

    async def analyze(self, fen: str, *, ascii_board: str | None = None) -> CoachAnalysis:
        position = CoachPosition.from_fen(fen, ascii_board=ascii_board)
        # Prompt reads must not block Agent Server's event loop in Studio.
        request = await asyncio.to_thread(_request_for, position, self.settings)
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
        return CoachAnalysis(
            text=response.output_text,
            response_id=response.id,
            model=response.model,
            position=position,
            usage=response.usage.model_dump() if response.usage else None,
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
