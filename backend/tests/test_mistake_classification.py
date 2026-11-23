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
from backend.coach.classification import CLASSIFICATION_VERSION, best_move_piece, current_classification, positional_details
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
    (category, motif) for category in ("tactical_miss", "tactical_allowed")
    for motif in ("hanging_piece", "fork", "pin_skewer", "discovered_attack")
] + [("other", None)])
@pytest.mark.parametrize("severity", ["inaccuracy", "mistake", "blunder"])
def test_supported_categories_and_subcategories_are_retained_for_errors(category, subcategory, severity):
    data = output_with({"category": category, "subcategory": subcategory})
    teaching = TeachingOutput.model_validate(data).validate_position(
        chess.STARTING_FEN, permitted_moves=position_evidence(chess.STARTING_FEN)["permitted_candidate_uci"])
    teaching.validate_move_evaluation(played_move="e2e4", evidence={**position_evidence(chess.STARTING_FEN), "move_quality": {"status": severity}})
    assert teaching.model_dump() == data


@pytest.mark.parametrize("classification", [
    "fork", [], {}, {"category": "tactical_miss"}, {"subcategory": "fork"},
    {"category": "psychological", "subcategory": None},
    {"category": "tactical_miss", "subcategory": "pawn_structure"},
    {"category": "positional", "subcategory": "fork"},
    {"category": "tactical_miss", "subcategory": "pin"},
    {"category": "positional", "subcategory": "knight", "reason": "extra"},
    {"category": "tactical_miss", "subcategory": ["fork", "hanging_piece"]},
    {"category": "positional", "subcategory": "knight"},
    {"category": "other", "subcategory": "knight"},
    {"category": "other"},
    {"category": "other", "subcategory": None, "played_piece": "pawn"},
])
def test_invalid_or_mixed_category_shapes_are_rejected(classification):
    with pytest.raises(ValueError):
        TeachingOutput.model_validate(output_with(classification))


@pytest.mark.parametrize("severity", ["good", "uncertain", "unknown", None])
def test_classification_is_forbidden_without_an_error_severity(severity):
    teaching = TeachingOutput.model_validate(output_with({"category": "tactical_miss", "subcategory": "fork"}))
    with pytest.raises(ValueError, match="reliable error severity"):
        teaching.validate_move_evaluation(played_move="e2e4", evidence={**position_evidence(chess.STARTING_FEN), "move_quality": {"status": severity}})


def test_classification_requires_a_played_move_and_nonempty_explanation():
    data = output_with({"category": "tactical_miss", "subcategory": "fork"})
    teaching = TeachingOutput.model_validate(data)
    with pytest.raises(ValueError):
        teaching.validate_move_evaluation(played_move=None, evidence={"move_quality": {"status": "blunder"}})
    data["move_evaluation"]["explanation"] = None
    with pytest.raises(ValueError):
        TeachingOutput.model_validate(data).validate_move_evaluation(
            played_move="e2e4", evidence={"move_quality": {"status": "blunder"}})


@pytest.mark.parametrize("severity", ["good", "uncertain", "unknown", None])
def test_null_classification_is_valid_without_an_error(severity):
    TeachingOutput.model_validate(output_with(None)).validate_move_evaluation(
        played_move="e2e4", evidence={**position_evidence(chess.STARTING_FEN), "move_quality": {"status": severity}})


@pytest.mark.parametrize("severity", ["inaccuracy", "mistake", "blunder"])
def test_null_classification_is_rejected_for_a_recorded_error(severity):
    with pytest.raises(ValueError, match="requires a mistake classification"):
        TeachingOutput.model_validate(output_with(None)).validate_move_evaluation(
            played_move="e2e4", evidence={"move_quality": {"status": severity}})


def test_approved_recommendation_can_still_receive_an_error_classification():
    # Candidate approval and player severity use different metrics.
    data = output_with({"category": "other", "subcategory": None})
    TeachingOutput.model_validate(data).validate_move_evaluation(
        played_move=data["candidate_moves"][0]["uci"], evidence={**position_evidence(chess.STARTING_FEN), "move_quality": {"status": "inaccuracy"}})


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
    for name, subcategory_type in (("TacticalMistake", "string"), ("OtherMistake", "null")):
        variant = schema["$defs"][name]
        assert variant["properties"]["subcategory"]["type"] == subcategory_type
        assert set(variant["required"]) == {"category", "subcategory"}
        assert variant["additionalProperties"] is False
    message = request["input"][1]["content"]
    payload = json.loads(message.split("Stockfish position evidence:\n")[1].split("\n\n")[0])
    assert payload["engine_verified_moves"] == evidence["top_moves"]
    assert "mistake_classification" not in payload
    assert "engine_best_move_piece" not in payload
    assert "PositionalMistake" not in schema["$defs"]
    assert all(field not in json.dumps(schema) for field in ("best_move_piece", "played_piece", "same_piece"))
    assert schema["$defs"]["TacticalMistake"]["properties"]["category"]["enum"] == ["tactical_miss", "tactical_allowed"]
    assert "move_quality.status" in message and "mistake_classification null" in message


@pytest.mark.parametrize("model", ["gpt-6-astra", "gpt-6.1-terra"])
@pytest.mark.parametrize("classification,played_move,saved_classification", [
    ({"category": "tactical_miss", "subcategory": "fork"}, "e2e4",
     {"category": "tactical_miss", "subcategory": "fork"}),
    ({"category": "tactical_allowed", "subcategory": "pin_skewer"}, "e2e4",
     {"category": "tactical_allowed", "subcategory": "pin_skewer"}),
    ({"category": "other", "subcategory": None}, "e2e4",
     {"category": "positional", "subcategory": "knight", "best_move_piece": "knight", "played_piece": "pawn", "same_piece": False}),
    ({"category": "other", "subcategory": None}, "g1f3",
     {"category": "positional", "subcategory": "knight", "best_move_piece": "knight", "played_piece": "knight", "same_piece": True}),
    ({"category": "other", "subcategory": None}, "b1c3",
     {"category": "positional", "subcategory": "knight", "best_move_piece": "knight", "played_piece": "knight", "same_piece": False}),
])
def test_single_response_preserves_classification_through_database_json_and_http(model, classification, played_move, saved_classification):
    data = output_with(classification)
    calls = []

    def upstream(request):
        calls.append(json.loads(request.content))
        return httpx2.Response(200, json=response_with(data, model))

    async def run():
        async with mock_client(upstream) as client:
            return await Coach(client, CoachSettings(model=model), position_engine=position_evidence,
                               engine=error_evidence).analyze(chess.STARTING_FEN, played_move=played_move)

    result = asyncio.run(run())
    assert len(calls) == 1 and result.move_analysis is None
    saved_data = {**data, "move_evaluation": {**data["move_evaluation"], "mistake_classification": saved_classification}}
    assert result.position_analysis["structured"] == saved_data
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
    assert stored["structured"] == saved_data
    assert stored["classification_version"] == CLASSIFICATION_VERSION
    restored = AnalyzePositionResponse(fen=result.position.fen, played_move=result.played_move,
        text=result.text, model=result.model, response_id=result.response_id, created_at=datetime.now(timezone.utc),
        teaching=stored["structured"], stockfish=params[8].obj, position_evidence=stored["engine_evidence"])
    assert restored.model_dump()["teaching"]["move_evaluation"]["mistake_classification"] == saved_classification


def test_classification_on_good_move_fails_the_run_before_persistence():
    async def run():
        async with mock_client(lambda request: httpx2.Response(200, json=response_with(
            output_with({"category": "tactical_miss", "subcategory": "fork"})))) as client:
            with pytest.raises(CoachResponseError):
                await Coach(client, position_engine=position_evidence, engine=good_move_evidence).analyze(
                    chess.STARTING_FEN, played_move="e2e4")
    asyncio.run(run())


@pytest.mark.parametrize("classification,saved_classification", [
    ({"category": "tactical_miss", "subcategory": "hanging_piece"},
     {"category": "tactical_miss", "subcategory": "hanging_piece"}),
    ({"category": "other", "subcategory": None},
     {"category": "positional", "subcategory": "knight", "best_move_piece": "knight", "played_piece": "pawn", "same_piece": False}),
])
def test_mistake_classification_persists_and_restores_after_restart(test_db_url, classification, saved_classification):
    db = Database(test_db_url)
    game = normalize_game(raw_game(), "alice")
    db.save_import("alice", [game], 1)
    data = output_with(classification)
    saved_data = {**data, "move_evaluation": {**data["move_evaluation"], "mistake_classification": saved_classification}}
    factory = mock_coach_factory(lambda request: httpx2.Response(200, json=response_with(data)), engine=error_evidence)
    with TestClient(create_app(test_db_url, coach_factory=factory)) as client:
        response = client.post('/api/coach/analyze', json={"game_id": game["id"], "ply": 0})
        assert response.status_code == 200
        saved = response.json()
        assert saved["teaching"] == saved_data
        assert saved["classification_current"] is True and saved["classification_version"] == CLASSIFICATION_VERSION
    with db.connection() as conn:
        row = conn.execute("SELECT position_analysis FROM coach_feedback").fetchone()
        assert row["position_analysis"]["structured"] == saved_data
    with TestClient(create_app(test_db_url, coach_factory=factory)) as restarted:
        assert restarted.get(f'/api/games/{game["id"]}').json()["coach_responses"]["0"] == saved
        assert restarted.get('/api/coach/feedback', params={"fen": chess.STARTING_FEN, "played_move": "e2e4"}).json() == saved


@pytest.mark.parametrize("category,subcategory", [
    ("tactical", "fork"), ("tactical", None), ("positional", "piece_play"),
    ("positional", "defending"), ("positional", None),
])
def test_legacy_labels_remain_readable_but_are_not_reinterpreted(category, subcategory):
    data = output_with({"category": category, "subcategory": subcategory})
    with pytest.raises(ValueError):
        TeachingOutput.model_validate(data)
    restored = TeachingAnalysis.model_validate(data)
    assert restored.move_evaluation.mistake_classification is None
    assert restored.positional_thesis == data["positional_thesis"]
    assert restored.move_evaluation.explanation == data["move_evaluation"]["explanation"]


@pytest.mark.parametrize("category", ["tactical_miss", "tactical_allowed", "positional"])
def test_new_classifications_cannot_have_null_subcategory(category):
    with pytest.raises(ValueError):
        TeachingOutput.model_validate(output_with({"category": category, "subcategory": None}))


@pytest.mark.parametrize("fen,uci,piece", [
    (chess.STARTING_FEN, "e2e4", "pawn"),
    (chess.STARTING_FEN, "g1f3", "knight"),
    ("4k3/8/8/8/8/8/8/RNBQK3 w Q - 0 1", "c1f4", "bishop"),
    ("4k3/8/8/8/8/8/8/RNBQK3 w Q - 0 1", "a1a4", "rook"),
    ("4k3/8/8/8/8/8/8/RNBQK3 w Q - 0 1", "d1d4", "queen"),
    ("4k3/8/8/8/8/8/8/RNBQK3 w Q - 0 1", "e1f1", "king"),
    ("r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1", "e8g8", "king"),
    ("8/P6k/8/8/8/8/8/4K3 w - - 0 1", "a7a8q", "pawn"),
])
def test_positional_piece_uses_original_board_including_castling_and_promotion(fen, uci, piece):
    evidence = {"fen": fen, "perspective": "White" if chess.Board(fen).turn else "Black",
                "top_moves": [{"rank": 1, "uci": uci, "depth": 18, "score": {"bound": "exact"}}]}
    assert best_move_piece(fen, evidence) == piece
    teaching = TeachingOutput.model_validate(output_with({"category": "other", "subcategory": None}))
    teaching.validate_move_evaluation(played_move=uci, evidence={"move_quality": {"status": "mistake"}})
    saved = teaching.as_analysis(fen, played_move=uci, evidence=evidence)
    assert saved.move_evaluation.mistake_classification.model_dump() == {
        "category": "positional", "subcategory": piece, "best_move_piece": piece, "played_piece": piece, "same_piece": True}


def test_piece_label_ignores_selected_candidates_and_played_piece_but_checks_engine_rank():
    evidence = position_evidence(chess.STARTING_FEN)
    evidence["top_moves"] = list(reversed(evidence["top_moves"]))
    data = output_with({"category": "other", "subcategory": None})
    data["candidate_moves"][0]["uci"] = "e2e4"
    teaching = TeachingOutput.model_validate(data)
    teaching.validate_move_evaluation(played_move="d2d4", evidence={"move_quality": {"status": "mistake"}})
    saved = teaching.as_analysis(chess.STARTING_FEN, played_move="d2d4", evidence=evidence)
    assert saved.move_evaluation.mistake_classification.model_dump() == {
        "category": "positional", "subcategory": "knight", "best_move_piece": "knight", "played_piece": "pawn", "same_piece": False}
    evidence["top_moves"] = [move for move in evidence["top_moves"] if move["rank"] != 1]
    with pytest.raises(ValueError, match="top-ranked"):
        teaching.as_analysis(chess.STARTING_FEN, played_move="d2d4", evidence=evidence)
    assert best_move_piece(chess.STARTING_FEN, evidence) is None


@pytest.mark.parametrize("played,best,played_piece,best_piece,same", [
    ("e2e3", "e2e4", "pawn", "pawn", True),
    ("d2d4", "e2e4", "pawn", "pawn", False),
    ("g1f3", "g1h3", "knight", "knight", True),
    ("b1c3", "g1f3", "knight", "knight", False),
    ("g1f3", "e2e4", "knight", "pawn", False),
])
def test_piece_identity_compares_origin_not_piece_type(played, best, played_piece, best_piece, same):
    evidence = position_evidence(chess.STARTING_FEN, preferred=[best])
    assert positional_details(chess.STARTING_FEN, played, evidence) == {
        "best_move_piece": best_piece, "played_piece": played_piece, "same_piece": same}


def test_old_positional_record_loads_without_inventing_metadata_but_needs_new_coaching():
    data = output_with({"category": "positional", "subcategory": "knight"})
    assert TeachingAnalysis.model_validate(data).model_dump() == data
    assert not current_classification({"classification_version": 2, "teaching": data})


@pytest.mark.parametrize("field", ["best_move_piece", "played_piece", "same_piece"])
def test_partial_positional_metadata_is_rejected(field):
    classification = {"category": "positional", "subcategory": "knight", "best_move_piece": "knight",
                      "played_piece": "pawn", "same_piece": False}
    del classification[field]
    with pytest.raises(ValueError):
        TeachingAnalysis.model_validate(output_with(classification))
