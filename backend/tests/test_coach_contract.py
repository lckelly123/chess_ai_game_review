import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from unittest.mock import Mock

import chess
import httpx2
import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from backend.chess_games import normalize_game, replay
from backend.coach import Coach, CoachAnalysis, CoachPosition, InvalidPositionError
from backend.coach.context import (
    COACH_CONTRACT_VERSION, context_key, current_coaching,
    previous_move_from_replay, validate_previous_move,
)
from backend.coach.classification import CLASSIFICATION_VERSION, lesson_classification
from backend.coach.move_quality import prepare_position_evidence
from backend.coach.responses import build_request
from backend.coach.routes import AnalyzePositionResponse
from backend.coach.teaching import TeachingOutput
from backend.database import Database
from backend.main import create_app
from backend.tests.position_fixtures import position_evidence
from backend.tests.test_app import raw_game
from backend.tests.test_coach import completed_response, teaching_output
from backend.tests.test_coach_graph import mock_client
from backend.tests.test_coach_routes import mock_coach_factory
from backend.tests.test_move_coach import evidence as played_evidence


def test_candidates_use_player_inaccuracy_boundary_without_relying_on_wdl():
    evidence = position_evidence(chess.STARTING_FEN)
    for move, cp in zip(evidence["top_moves"], [0, -54, -55, -200, -500]):
        move["score"]["cp"] = cp
        # All WDL outcomes agree; the new candidate policy must still filter.
        move["wdl"] = {"wins": 500, "draws": 0, "losses": 500}
    snapshot = deepcopy(evidence)
    prepared = prepare_position_evidence(evidence)
    assert prepared["permitted_candidate_uci"] == [move["uci"] for move in evidence["top_moves"][:2]]
    assert prepared["top_moves"][2]["quality"]["status"] == "inaccuracy"
    assert len(prepared["top_moves"]) == 5
    assert prepared["sharpness"]["capped_scores_cp"] == [0, -54, -55, -200, -500]
    assert evidence == snapshot


def test_candidate_limit_mates_and_unreliable_scores():
    evidence = position_evidence(chess.STARTING_FEN)
    assert len(evidence["permitted_candidate_uci"]) == 3
    for move, mate, cp in zip(evidence["top_moves"], [3, 8, None, None, -2], [None, None, 1100, 600, None]):
        move["score"].update(mate=mate, cp=cp)
    prepared = prepare_position_evidence(evidence)
    assert prepared["permitted_candidate_uci"] == [move["uci"] for move in evidence["top_moves"][:2]]
    evidence["top_moves"][1]["score"]["bound"] = "lower"
    assert prepare_position_evidence(evidence)["permitted_candidate_uci"] == [evidence["top_moves"][0]["uci"]]
    evidence["top_moves"][0]["depth"] = 0
    assert prepare_position_evidence(evidence)["permitted_candidate_uci"] == []


def test_compact_request_keeps_full_internal_evidence_and_small_dynamic_input():
    evidence = position_evidence(chess.STARTING_FEN)
    snapshot = deepcopy(evidence)
    request = build_request(chess.STARTING_FEN, evidence=evidence, played_move="g1h3")
    message = request["input"][1]["content"]
    assert message.startswith("Side to move: White\n\nOpponent's previous move: unavailable\n\nFEN: ")
    assert "Severity: good" in message and "SAN: Nh3" in message
    assert "pv_uci" not in message and "probabilities" not in message and "move_quality_policy" not in message
    assert "UCI | Evaluation | PV (SAN)" in message
    assert len(message) < 1000  # Fixed one-ply fixture previously exceeded 8,000 characters.
    assert evidence == snapshot and len(evidence["top_moves"]) == 5
    schema = request["text"]["format"]["schema"]
    assert set(schema["$defs"]["MoveEvaluation"]["properties"]) == {"explanation", "mistake_classification"}


@pytest.mark.parametrize("mutate", [lambda moves: moves[:-1], lambda moves: list(reversed(moves))])
def test_returned_candidates_must_match_the_exact_supplied_order(mutate):
    data = teaching_output()
    data["candidate_moves"] = mutate(data["candidate_moves"])
    with pytest.raises(ValueError, match="every supplied move"):
        TeachingOutput.model_validate(data).validate_position(chess.STARTING_FEN,
            permitted_moves=position_evidence(chess.STARTING_FEN)["permitted_candidate_uci"])


def test_good_fourth_ranked_move_still_requires_its_own_explanation():
    evidence = position_evidence(chess.STARTING_FEN)
    played = evidence["top_moves"][3]["uci"]
    assert played not in evidence["permitted_candidate_uci"]
    output = TeachingOutput.model_validate(teaching_output())
    output.validate_move_evaluation(played_move=played, evidence={"move_quality": {"status": "good"}})
    output.move_evaluation.explanation = None
    with pytest.raises(ValueError, match="good supplied candidate"):
        output.validate_move_evaluation(played_move=played, evidence={"move_quality": {"status": "good"}})


def test_previous_move_is_validated_and_san_is_derived_on_the_preceding_board():
    detail = replay("1. e4 e5 2. Nf3 *")
    previous = previous_move_from_replay(detail, 2)
    assert previous["uci"] == "e7e5" and previous["san"] == "e5"
    assert validate_previous_move(detail["positions"][2]["fen"], {**previous, "san": "Qh4#"}) == previous
    assert previous_move_from_replay(detail, 0) is None
    with pytest.raises(InvalidPositionError):
        validate_previous_move(chess.STARTING_FEN, previous)


def test_previous_context_is_not_reused_in_a_checkpointed_thread():
    requests = []
    def upstream(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(200, json=completed_response(request=request))

    async def run():
        async with mock_client(upstream) as client:
            graph = Coach(client, position_engine=position_evidence).graph.builder.compile(checkpointer=InMemorySaver())
            detail = replay("1. e4 e5 *")
            config = {"configurable": {"thread_id": "previous-move"}}
            await graph.ainvoke({"fen": detail["positions"][2]["fen"],
                                 "previous_move": previous_move_from_replay(detail, 2)}, config)
            await graph.ainvoke({"fen": chess.STARTING_FEN}, config)
    asyncio.run(run())
    assert "Opponent's previous move: e5 (e7e5)" in requests[0]["input"][1]["content"]
    assert "Opponent's previous move: unavailable" in requests[1]["input"][1]["content"]


def test_bad_history_is_rejected_before_engine_or_model_work(monkeypatch):
    engine = Mock(side_effect=AssertionError("Must reject invalid context first"))
    monkeypatch.setattr('backend.coach.responses.analyze_position', engine)
    with pytest.raises(InvalidPositionError):
        build_request(chess.STARTING_FEN, previous_move={"fen": chess.STARTING_FEN, "uci": "e2e4"})
    async def run():
        async with mock_client(engine) as client:
            with pytest.raises(InvalidPositionError):
                await Coach(client, position_engine=engine).analyze(chess.STARTING_FEN,
                    previous_move={"fen": chess.STARTING_FEN, "uci": "e2e4"})
    asyncio.run(run())
    engine.assert_not_called()


def test_history_specific_reviews_restore_independently_and_unknown_history_never_matches(test_db_url):
    db = Database(test_db_url)
    games = [normalize_game(raw_game(index, pgn='[White "alice"]\n[Black "bob"]\n[Result "1-0"]\n\n' + moves), "alice")
             for index, moves in enumerate(("1. Nf3 Nf6 2. Nc3 Nc6 3. e4 1-0", "1. Nc3 Nc6 2. Nf3 Nf6 3. e4 1-0"), 10)]
    db.save_import("alice", games, 1)
    details = [replay(game["pgn"]) for game in games]
    fen = details[0]["positions"][4]["fen"]
    assert fen == details[1]["positions"][4]["fen"]
    calls = []
    def upstream(request):
        calls.append(json.loads(request.content))
        return httpx2.Response(200, json=completed_response(request=request, id=f"resp_{len(calls)}"))
    with TestClient(create_app(test_db_url, coach_factory=mock_coach_factory(upstream, engine=played_evidence))) as client:
        first = client.post('/api/coach/analyze', json={"game_id": games[0]["id"], "ply": 4})
        assert first.status_code == 200, first.text
        assert first.json()["previous_move"]["san"] == "Nc6"
        assert first.json()["coach_current"] is True
        assert client.get(f'/api/games/{games[1]["id"]}').json()["coach_responses"] == {}
        assert client.get('/api/coach/feedback', params={"fen": fen, "played_move": "e2e4"}).json() is None
        second = client.post('/api/coach/analyze', json={"game_id": games[1]["id"], "ply": 4})
        assert second.status_code == 200, second.text
        assert second.json()["previous_move"]["san"] == "Nf6"
    with TestClient(create_app(test_db_url)) as client:
        for game, answer in zip(games, (first.json(), second.json())):
            assert client.get(f'/api/games/{game["id"]}').json()["coach_responses"]["4"] == answer
            params = {"fen": fen, "played_move": "e2e4", "game_id": game["id"], "ply": 4}
            assert client.get('/api/coach/feedback', params=params).json() == answer
    assert len(calls) == 2


def test_legacy_fallback_remains_readable_but_cannot_satisfy_current_contract(test_db_url):
    db = Database(test_db_url)
    detail = replay("1. e4 e5 *")
    position = CoachPosition.from_fen(detail["positions"][1]["fen"])
    old = CoachAnalysis("Old review", "old", "model", position, None, played_move="e7e5",
                        position_analysis={"classification_version": CLASSIFICATION_VERSION, "structured": teaching_output(position.fen)})
    db.save_coach_feedback(old)
    key = (position.fen, "e7e5", context_key(previous_move_from_replay(detail, 1)))
    restored = db.coach_feedback_for_reviews([key])[key]
    assert restored["text"] == "Old review" and lesson_classification(restored)
    assert not current_coaching(restored)
    assert current_coaching({**restored, "coach_contract_version": COACH_CONTRACT_VERSION})


def test_comparison_target_is_derived_from_engine_evidence_outside_model_output():
    position = position_evidence(chess.STARTING_FEN)
    played = {**deepcopy(position["top_moves"][0]), "uci": "e2e4", "score": {"cp": -200, "mate": None, "bound": "exact"}}
    response = AnalyzePositionResponse(fen=chess.STARTING_FEN, played_move="e2e4", text="Review", model="model",
        response_id="test", created_at=datetime.now(timezone.utc), teaching=teaching_output(), position_evidence=position,
        stockfish={"top_moves": position["top_moves"], "played_move": played})
    assert response.better_candidate_uci == position["permitted_candidate_uci"][0]
    assert "better_candidate_uci" not in response.teaching.move_evaluation.model_dump()
    response.stockfish["move_quality"]["status"] = "uncertain"
    assert response.better_candidate_uci is None
