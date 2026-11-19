import asyncio
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import Mock

import chess
import httpx2
import pytest
from fastapi.testclient import TestClient

from backend.chess_games import normalize_game
from backend.coach import Coach, CoachResponseError, CoachSettings
from backend.coach.player_move_quality import assess_player_move
from backend.coach.responses import build_request
from backend.coach.routes import AnalyzePositionResponse
from backend.coach.teaching import TeachingAnalysis, TeachingOutput
from backend.database import Database
from backend.main import create_app
from backend.tests.position_fixtures import position_evidence
from backend.tests.test_app import raw_game
from backend.tests.test_coach import completed_response, teaching_output
from backend.tests.test_coach_graph import mock_client
from backend.tests.test_coach_routes import mock_coach_factory
from backend.tests.test_move_coach import evidence as good_move_evidence


def output_with(classification):
    data = teaching_output()
    data["move_evaluation"].update(
        explanation="The move allows a material loss in the supplied continuation.",
        mistake_classification=classification,
    )
    return data


def error_evidence(review, position):
    result = good_move_evidence(review, position)
    result["played_move"]["score"]["cp"] = -200
    result["move_quality"] = assess_player_move(position["top_moves"][0], result["played_move"])
    result["played_move"]["quality"] = result["move_quality"]
    return result


def response_with(data, model="gpt-6-astra"):
    result = completed_response(model=model)
    result["output"][1]["content"][0]["text"] = json.dumps(data)
    return result


@pytest.mark.parametrize("category,subcategory", [
    ("tactical", None), ("tactical", "hanging_piece"), ("tactical", "fork"), ("tactical", "discovered_attack"),
    ("positional", None), ("positional", "pawn_structure"), ("positional", "piece_play"),
    ("positional", "defending"), ("positional", "attacking"),
])
@pytest.mark.parametrize("severity", ["inaccuracy", "mistake", "blunder"])
def test_supported_categories_and_subcategories_are_retained_for_errors(category, subcategory, severity):
    data = output_with({"category": category, "subcategory": subcategory})
    teaching = TeachingOutput.model_validate(data).validate_position(
        chess.STARTING_FEN, permitted_moves=position_evidence(chess.STARTING_FEN)["permitted_candidate_uci"])
    teaching.validate_move_evaluation(played_move="e2e4", evidence={"move_quality": {"status": severity}})
    assert teaching.model_dump() == data


@pytest.mark.parametrize("classification", [
    "fork", [], {}, {"category": "tactical"}, {"subcategory": "fork"},
    {"category": "psychological", "subcategory": None},
    {"category": "tactical", "subcategory": "pawn_structure"},
    {"category": "positional", "subcategory": "fork"},
    {"category": "tactical", "subcategory": "pin"},
    {"category": "positional", "subcategory": "piece_play", "reason": "extra"},
    {"category": "tactical", "subcategory": ["fork", "hanging_piece"]},
])
def test_invalid_or_mixed_category_shapes_are_rejected(classification):
    with pytest.raises(ValueError):
        TeachingOutput.model_validate(output_with(classification))


@pytest.mark.parametrize("severity", ["good", "uncertain", "unknown", None])
def test_classification_is_forbidden_without_an_error_severity(severity):
    teaching = TeachingOutput.model_validate(output_with({"category": "tactical", "subcategory": "fork"}))
    with pytest.raises(ValueError, match="reliable error severity"):
        teaching.validate_move_evaluation(played_move="e2e4", evidence={"move_quality": {"status": severity}})


def test_classification_requires_a_played_move_and_nonempty_explanation():
    data = output_with({"category": "tactical", "subcategory": None})
    teaching = TeachingOutput.model_validate(data)
    with pytest.raises(ValueError):
        teaching.validate_move_evaluation(played_move=None, evidence={"move_quality": {"status": "blunder"}})
    data["move_evaluation"]["explanation"] = None
    with pytest.raises(ValueError):
        TeachingOutput.model_validate(data).validate_move_evaluation(
            played_move="e2e4", evidence={"move_quality": {"status": "blunder"}})


@pytest.mark.parametrize("severity", ["good", "inaccuracy", "mistake", "blunder", "uncertain", None])
def test_null_classification_does_not_force_a_label(severity):
    TeachingOutput.model_validate(output_with(None)).validate_move_evaluation(
        played_move="e2e4", evidence={"move_quality": {"status": severity}})


def test_approved_recommendation_can_still_receive_an_error_classification():
    # Candidate approval and player severity use different metrics.
    data = output_with({"category": "positional", "subcategory": "piece_play"})
    TeachingOutput.model_validate(data).validate_move_evaluation(
        played_move=data["candidate_moves"][0]["uci"], evidence={"move_quality": {"status": "inaccuracy"}})


def test_new_schema_requires_field_but_old_saved_reviews_default_to_null():
    old = output_with(None)
    del old["move_evaluation"]["mistake_classification"]
    with pytest.raises(ValueError):
        TeachingOutput.model_validate(old)
    restored = TeachingAnalysis.model_validate(old)
    assert restored.move_evaluation.mistake_classification is None
    assert restored.move_evaluation.explanation == old["move_evaluation"]["explanation"]


def test_request_schema_constrains_categories_and_preserves_existing_inputs():
    evidence = position_evidence(chess.STARTING_FEN)
    request = build_request(chess.STARTING_FEN, evidence=evidence)
    schema = request["text"]["format"]["schema"]
    evaluation = schema["$defs"]["MoveEvaluation"]
    assert "mistake_classification" in evaluation["required"]
    assert evaluation["additionalProperties"] is False
    for name, category in [("TacticalMistake", "tactical"), ("PositionalMistake", "positional")]:
        variant = schema["$defs"][name]
        assert variant["properties"]["category"]["const"] == category
        assert set(variant["required"]) == {"category", "subcategory"}
        assert variant["additionalProperties"] is False
    message = request["input"][1]["content"]
    payload = json.loads(message.split("Stockfish position evidence:\n")[1].split("\n\n")[0])
    assert payload["engine_verified_moves"] == evidence["top_moves"]
    assert "mistake_classification" not in payload
    assert "move_quality.status" in message and "mistake_classification null" in message


@pytest.mark.parametrize("model", ["gpt-6-astra", "gpt-6.1-terra"])
@pytest.mark.parametrize("classification", [None, {"category": "tactical", "subcategory": "fork"},
                                           {"category": "positional", "subcategory": None}])
def test_single_response_preserves_classification_through_database_json_and_http(model, classification):
    data = output_with(classification)
    calls = []

    def upstream(request):
        calls.append(json.loads(request.content))
        return httpx2.Response(200, json=response_with(data, model))

    async def run():
        async with mock_client(upstream) as client:
            return await Coach(client, CoachSettings(model=model), position_engine=position_evidence,
                               engine=error_evidence).analyze(chess.STARTING_FEN, played_move="e2e4")

    result = asyncio.run(run())
    assert len(calls) == 1 and result.move_analysis is None
    assert result.position_analysis["structured"] == data
    # Exercise the real repository's Jsonb binding without a database service.
    connection = Mock()
    @contextmanager
    def connect():
        yield connection
    db = object.__new__(Database)
    db.connection = connect
    db.save_coach_feedback(result)
    sql, params = connection.execute.call_args.args
    assert "position_analysis -> 'structured' AS teaching" in sql
    stored = json.loads(json.dumps(params[6].obj))
    assert stored["structured"] == data
    restored = AnalyzePositionResponse(fen=result.position.fen, played_move=result.played_move,
        text=result.text, model=result.model, response_id=result.response_id, created_at=datetime.now(timezone.utc),
        teaching=stored["structured"], stockfish=params[8].obj, position_evidence=stored["engine_evidence"])
    assert restored.model_dump()["teaching"]["move_evaluation"]["mistake_classification"] == classification


def test_classification_on_good_move_fails_the_run_before_persistence():
    async def run():
        async with mock_client(lambda request: httpx2.Response(200, json=response_with(
            output_with({"category": "tactical", "subcategory": "fork"})))) as client:
            with pytest.raises(CoachResponseError):
                await Coach(client, position_engine=position_evidence, engine=good_move_evidence).analyze(
                    chess.STARTING_FEN, played_move="e2e4")
    asyncio.run(run())


def test_mistake_classification_persists_and_restores_after_restart(test_db_url):
    db = Database(test_db_url)
    game = normalize_game(raw_game(), "alice")
    db.save_import("alice", [game], 1)
    data = output_with({"category": "tactical", "subcategory": "hanging_piece"})
    factory = mock_coach_factory(lambda request: httpx2.Response(200, json=response_with(data)), engine=error_evidence)
    with TestClient(create_app(test_db_url, coach_factory=factory)) as client:
        response = client.post('/api/coach/analyze', json={"game_id": game["id"], "ply": 0})
        assert response.status_code == 200
        saved = response.json()
        assert saved["teaching"] == data
    with db.connection() as conn:
        row = conn.execute("SELECT position_analysis FROM coach_feedback").fetchone()
        assert row["position_analysis"]["structured"] == data
    with TestClient(create_app(test_db_url, coach_factory=factory)) as restarted:
        assert restarted.get(f'/api/games/{game["id"]}').json()["coach_responses"]["0"] == saved
        assert restarted.get('/api/coach/feedback', params={"fen": chess.STARTING_FEN, "played_move": "e2e4"}).json() == saved
