"""One Responses call in its own LangGraph, also available in Studio."""

import asyncio
import json
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from langsmith.run_helpers import is_traceable_function
from langsmith.wrappers import wrap_openai
from typing_extensions import TypedDict

from ..coach.responses import CoachResponseError, open_response_client
from ..coach.settings import CoachSettings
from .output import MultiGameReport

MODEL = "gpt-6-astra"
REASONING_EFFORT = "xhigh"
PROMPT = Path(__file__).with_name("prompt.md")


class MultiGameInput(TypedDict):
    summary: dict[str, Any]
    mistakes_by_category: list[dict[str, Any]]


class MultiGameState(MultiGameInput):
    report: dict[str, Any]
    response_id: str
    model: str
    usage: dict[str, Any] | None


def build_request(payload: MultiGameInput, settings: CoachSettings | None = None) -> dict:
    settings = settings or CoachSettings.from_env()
    return {
        "model": MODEL, "reasoning": {"effort": REASONING_EFFORT},
        "max_output_tokens": settings.max_output_tokens, "store": False,
        # Fail visibly rather than silently dropping mistakes from the context.
        "truncation": "disabled",
        "text": {"format": {"type": "json_schema", "name": "multi_game_report", "strict": True,
                            "schema": MultiGameReport.model_json_schema()}},
        "input": [
            {"role": "system", "content": PROMPT.read_text(encoding="utf-8")},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }


async def analyze_with_client(client, payload: MultiGameInput, settings: CoachSettings | None = None) -> dict:
    if not is_traceable_function(client.responses.create):
        wrap_openai(client, chat_name="Multi-game OpenAI Responses")
    request = await asyncio.to_thread(build_request, payload, settings)
    response = await client.responses.create(**request)
    if response.status != "completed" or not response.output_text.strip():
        raise CoachResponseError("Multi-game analysis returned no complete answer.", response.id)
    if any(part.type == "refusal" for item in response.output if item.type == "message" for part in item.content):
        raise CoachResponseError("The model declined this analysis.", response.id)
    try:
        report = MultiGameReport.model_validate_json(response.output_text)
    except ValueError as exc:
        raise CoachResponseError("Multi-game analysis returned an invalid report.", response.id) from exc
    return {"report": report.model_dump(), "response_id": response.id, "model": response.model,
            "usage": response.usage.model_dump() if response.usage else None}


async def analyze_from_environment(payload: MultiGameInput) -> dict:
    settings = CoachSettings.from_env(model=MODEL)
    async with open_response_client(settings) as client:
        return await analyze_with_client(client, payload, settings)


def build_multi_game_graph(analyze=None):
    analyze = analyze or analyze_from_environment

    async def analyze_patterns(state: MultiGameInput) -> dict:
        # Explicit input projection prevents an earlier Studio report leaking into a rerun.
        payload = {"summary": state["summary"], "mistakes_by_category": state["mistakes_by_category"]}
        if not payload["summary"].get("errors", {}).get("total"):
            raise ValueError("Analyze a game with recorded mistakes before running multi-game analysis.")
        return await analyze(payload)

    builder = StateGraph(MultiGameState, input_schema=MultiGameInput)
    builder.add_node("analyze_patterns", analyze_patterns)
    builder.add_edge(START, "analyze_patterns")
    builder.add_edge("analyze_patterns", END)
    return builder.compile(name="multi_game_coach")


graph = build_multi_game_graph()
