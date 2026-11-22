from copy import deepcopy
from datetime import datetime, timezone
import math

import chess
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import Mock

from backend.coach.move_quality import prepare_position_evidence
from backend.coach.player_move_quality import assess_player_move, classify_loss, win_chance, with_player_move_quality
from backend.coach.routes import AnalyzePositionResponse, create_coach_router
from backend.tests.position_fixtures import position_evidence


def cp(value, depth=18, bound="exact"):
    return {"score": {"cp": value, "mate": None, "bound": bound}, "depth": depth}


def mate(value):
    return {"score": {"cp": None, "mate": value, "bound": "exact"}, "depth": 18}


@pytest.mark.parametrize("loss,status", [
    (0, "good"), (math.nextafter(5, 0), "good"), (5, "inaccuracy"),
    (math.nextafter(10, 0), "inaccuracy"), (10, "mistake"),
    (math.nextafter(15, 0), "mistake"), (15, "blunder"), (50, "blunder"),
])
def test_exact_severity_boundaries_without_rounding(loss, status):
    assert classify_loss(loss) == status


def test_logistic_curve_caps_and_draw_symmetry():
    assert win_chance(0) == 50
    assert win_chance(100) == pytest.approx(59.102589719)
    assert win_chance(-100) == pytest.approx(100 - win_chance(100))
    assert win_chance(1000000) == win_chance(1000)
    assert win_chance(-1000000) == win_chance(-1000)
    assert assess_player_move(cp(1500), cp(1000))["winning_chances_loss_pp"] == 0


@pytest.mark.parametrize("played,status", [(50,"good"), (0,"inaccuracy"), (-50,"mistake"), (-100,"blunder")])
def test_centipawn_severity_including_missed_opportunities(played, status):
    result = assess_player_move(cp(100), cp(played))
    assert result["status"] == status
    assert result["winning_chances_loss_pp"] == pytest.approx(win_chance(100) - win_chance(played))


def test_g5_example_is_good_using_cp_even_when_wdl_says_inferior():
    best, played = cp(187), cp(130)
    best["wdl"] = {"wins": 970, "draws": 30, "losses": 0}
    played["wdl"] = {"wins": 764, "draws": 236, "losses": 0}
    result = assess_player_move(best, played)
    assert result["status"] == "good"
    assert result["winning_chances_loss_pp"] == pytest.approx(4.818, abs=.01)
    del best["wdl"], played["wdl"]
    assert assess_player_move(best, played) == result


@pytest.mark.parametrize("best,played", [
    (cp(100),cp(101)), (cp(100),cp(0,17)), (cp(100),cp(0,bound="upper")),
    (cp(100),{}), (cp(100),cp(float('nan'))), (cp(True),cp(0)),
    (cp(100),{"score":{"cp":0,"mate":1,"bound":"exact"},"depth":18}),
    (cp(100),mate(1)), (mate(-5),cp(-100)), (mate(-5),mate(1)),
])
def test_unreliable_scores_do_not_get_a_severity_label(best, played):
    result = assess_player_move(best, played)
    assert result["status"] == "uncertain"
    assert result["winning_chances_loss_pp"] is None


@pytest.mark.parametrize("best,played,status,reason", [
    (cp(0),mate(-3),"blunder","mate_created"),
    (cp(-700),mate(-3),"blunder","mate_created"),
    (cp(-701),mate(-3),"mistake","mate_created"),
    (cp(-999),mate(0),"mistake","mate_created"),
    (cp(-1000),mate(-3),"inaccuracy","mate_created"),
    (mate(3),cp(700),"blunder","mate_lost"),
    (mate(3),cp(701),"mistake","mate_lost"),
    (mate(3),cp(999),"mistake","mate_lost"),
    (mate(3),cp(1000),"inaccuracy","mate_lost"),
    (mate(3),mate(-3),"blunder","mate_lost"),
    (mate(3),mate(0),"blunder","mate_lost"),
    (mate(3),mate(8),"good","mate_retained"),
    (mate(-3),mate(-1),"good","already_forced_loss"),
])
def test_mate_advice_is_separate_from_cp_formula(best, played, status, reason):
    assert assess_player_move(best, played) == {"status":status,"winning_chances_loss_pp":None,"reason":reason}


def test_player_severity_cannot_change_position_classification_or_candidate_approval():
    position = position_evidence(chess.STARTING_FEN)
    snapshot = deepcopy(position)
    # Sharpness and WDL candidate approval remain independent of player severity.
    prepared = prepare_position_evidence(position)
    assert prepared == snapshot
    for move in prepared["top_moves"]:
        assess_player_move(prepared["top_moves"][0], move)
    assert prepared == snapshot == position


def test_saved_labels_are_recomputed_from_scores_without_mutating_stored_evidence():
    old = {"perspective":"White", "top_moves":[cp(187)], "played_move":cp(130),
           "move_quality":{"status":"meaningfully_inferior","expected_score_loss_pp":10.3}}
    snapshot = deepcopy(old)
    result = with_player_move_quality(old)
    assert result["move_quality"]["status"] == "good"
    assert result["move_quality_policy"]["metric"] == "winning_chances_loss_pp"
    assert result["top_moves"] == old["top_moves"]
    assert old == snapshot
    assert with_player_move_quality({"played_move":cp(0)})["move_quality"]["status"] == "uncertain"

    saved = {"fen":chess.STARTING_FEN,"played_move":"e2e4","text":"Saved coaching.",
             "model":"gpt-6-astra","response_id":"old","created_at":datetime.now(timezone.utc),
             "stockfish":old,"position_evidence":position_evidence(chess.STARTING_FEN)}
    response = AnalyzePositionResponse(**saved)
    assert response.stockfish["move_quality"]["status"] == "good"
    assert response.position_evidence == saved["position_evidence"]
    assert response.text == saved["text"] and old == snapshot

    app = FastAPI()
    app.state.db = Mock()
    app.state.db.coach_feedback_for_reviews.return_value = {(chess.STARTING_FEN,"e2e4"):saved}
    app.include_router(create_coach_router())
    with TestClient(app) as client:
        data = client.get('/api/coach/feedback', params={"fen":chess.STARTING_FEN,"played_move":"e2e4"}).json()
    assert data["stockfish"]["move_quality"]["status"] == "good"
    assert data["position_evidence"] == saved["position_evidence"]
    app.state.db.save_coach_feedback.assert_not_called()
