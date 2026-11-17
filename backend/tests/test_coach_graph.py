import asyncio
import importlib
import json
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import Mock

import chess
import httpx2
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langsmith import Client, tracing_context
from openai import AsyncOpenAI, RateLimitError

from backend.coach import Coach, CoachConfigurationError, InvalidPositionError
from backend.coach.graph import graph
from backend.tests.test_coach import completed_response


@asynccontextmanager
async def mock_client(handler):
    async with AsyncOpenAI(
        api_key="test-key", max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    ) as client:
        yield client


def test_studio_config_loads_without_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LANGSMITH_API_KEY", "")
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / "langgraph.json").read_text())
    module, variable = config["graphs"]["chess_coach"].split(":")
    loaded = getattr(importlib.import_module(module), variable)
    assert loaded is graph
    assert set(loaded.get_input_jsonschema()["properties"]) == {"fen", "played_move"}
    assert {(edge.source, edge.target) for edge in loaded.get_graph().edges} == {
        ("__start__", "analyze_position"), ("analyze_position", "__end__"),
        ("analyze_position", "evaluate_move"), ("evaluate_move", "__end__"),
    }

    async def run():
        with pytest.raises(InvalidPositionError):
            await loaded.ainvoke({"fen": "invalid"})
        with pytest.raises(CoachConfigurationError, match="OPENAI_API_KEY"):
            await loaded.ainvoke({"fen": chess.STARTING_FEN})
    asyncio.run(run())


def test_studio_graph_uses_same_adapter_and_closes_client(monkeypatch):
    import backend.coach.graph as graph_module

    clients, requests = [], []

    def upstream(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(200, json=completed_response())

    @asynccontextmanager
    async def client_factory(settings):
        async with mock_client(upstream) as client:
            clients.append(client)
            yield client

    monkeypatch.setattr(graph_module, "open_response_client", client_factory)
    result = asyncio.run(graph.ainvoke({"fen": chess.STARTING_FEN}))
    assert result["response_id"] == "resp_test"
    assert result["side_to_move"] == "White"
    assert result["usage"]["total_tokens"] == 160
    assert json.loads(json.dumps(result)) == result
    assert len(requests) == 1
    assert requests[0]["store"] is False
    assert clients[0].is_closed()


def test_reused_studio_thread_does_not_send_previous_board_or_analysis():
    requests = []

    def upstream(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(200, json=completed_response())

    async def run():
        async with mock_client(upstream) as client:
            coach = Coach(client)
            persistent = coach.graph.builder.compile(checkpointer=InMemorySaver())
            config = {"configurable": {"thread_id": "studio-test"}}
            await persistent.ainvoke({"fen": chess.STARTING_FEN}, config=config)
            board = chess.Board()
            board.push_san("e4")
            fen = board.fen(en_passant="fen")
            result = await persistent.ainvoke({"fen": fen}, config=config)
            assert result["fen"] == fen
            assert result["side_to_move"] == "Black"
            assert fen in requests[1]["input"][1]["content"]
            assert "Test analysis" not in json.dumps(requests[1])
            assert len(requests) == 2
    asyncio.run(run())


@pytest.mark.parametrize("status", [200, 429])
def test_nested_langsmith_traces_use_local_recorder(status):
    # Record the actual LangSmith SDK calls without any network or credentials.
    recorder = Mock(spec=Client)
    requests = []

    def upstream(request):
        requests.append(request)
        body = completed_response() if status == 200 else {
            "error": {"message": "Rate limited", "type": "rate_limit_error"},
        }
        return httpx2.Response(status, json=body)

    async def run():
        async with mock_client(upstream) as client:
            coach = Coach(client)
            # Reusing a client must not add a second Responses trace wrapper.
            wrapped_create = client.responses.create
            coach = Coach(client)
            assert client.responses.create is wrapped_create
            with tracing_context(enabled=True, client=recorder, project_name="coach-test"):
                if status == 200:
                    await coach.analyze(chess.STARTING_FEN)
                else:
                    with pytest.raises(RateLimitError):
                        await coach.analyze(chess.STARTING_FEN)
    asyncio.run(run())

    starts = [call.kwargs for call in recorder.create_run.call_args_list]
    by_name = {run["name"]: run for run in starts}
    root = by_name["chess_coach"]
    node = by_name["analyze_position"]
    llm = by_name["OpenAI Responses"]
    assert node["parent_run_id"] == root["id"]
    assert llm["parent_run_id"] == node["id"]
    assert llm["run_type"] == "llm"
    assert len([run for run in starts if run["run_type"] == "llm"]) == 1
    assert llm["inputs"]["model"] == "gpt-6-astra"
    assert "test-key" not in repr(starts)
    assert len(requests) == 1
    updates = {
        call.args[0] if call.args else call.kwargs["run_id"]: call.kwargs
        for call in recorder.update_run.call_args_list
    }
    if status == 200:
        assert updates[llm["id"]]["outputs"]["usage_metadata"]["total_tokens"] == 160
        assert updates[root["id"]]["outputs"]["response_id"] == "resp_test"
    else:
        assert updates[llm["id"]]["error"]
        assert updates[node["id"]]["error"]
        assert updates[root["id"]]["error"]


def test_tracing_can_be_disabled_without_affecting_coach():
    recorder = Mock(spec=Client)

    async def run():
        async with mock_client(lambda request: httpx2.Response(200, json=completed_response())) as client:
            with tracing_context(enabled=False, client=recorder):
                result = await Coach(client).analyze(chess.STARTING_FEN)
                assert result.response_id == "resp_test"
    asyncio.run(run())
    recorder.create_run.assert_not_called()
    recorder.update_run.assert_not_called()
