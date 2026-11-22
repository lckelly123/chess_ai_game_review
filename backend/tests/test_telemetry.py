from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import Mock

import chess
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.coach.routes import AnalyzePositionResponse, create_coach_router
from backend.telemetry import classify_review


def evidence(fen=chess.STARTING_FEN, best="d2d4", played="e2e4", reply="e7e5", best_cp=300, played_cp=0):
    def candidate(uci, pv, cp, rank):
        return {"uci": uci, "rank": rank, "depth": 18, "score": {"cp": cp, "mate": None, "bound": "exact"}, "pv_uci": pv}
    return {"fen": fen, "perspective": "White" if chess.Board(fen).turn else "Black",
            "top_moves": [candidate(best, [best], best_cp, 1)],
            "played_move": candidate(played, [played, reply] if reply else [played], played_cp, None)}


@pytest.mark.parametrize("fen,best,played,reply,motif", [
    ("3rk3/8/8/8/8/8/8/3QK3 w - - 0 1", "d1c2", "d1d5", "d8d5", "hung_piece"),
    ("3qk3/8/8/8/8/8/8/3RK3 b - - 0 1", "d8c7", "d8d4", "d1d4", "hung_piece"),
    ("r3k3/8/8/1N6/8/8/8/4K3 w - - 0 1", "b5c7", "e1d1", "a8a7", "missed_fork"),
    ("4k3/8/8/8/1n6/8/7P/R3K3 w Q - 0 1", "a1a2", "h2h3", "b4c2", "allowed_fork"),
    ("8/8/8/p1p5/2P5/1P2k3/2K5/8 b - - 0 1", "e3f3", "e3e2", "c2c3", "endgame_technique"),
    (chess.STARTING_FEN, "d2d4", "e2e4", "e7e5", "other"),
])
def test_original_motifs_from_existing_root_variations(fen, best, played, reply, motif):
    stockfish = evidence(fen, best, played, reply)
    original = deepcopy(stockfish)
    result = classify_review(fen, played, stockfish)
    assert result.status == "classified"
    assert result.motif == motif
    assert result.cp_loss == 300
    assert stockfish == original


@pytest.mark.parametrize("best_cp,played_cp,status,loss", [
    (199, 0, "below_threshold", 199), (200, 0, "classified", 200),
    (1500, 1100, "below_threshold", 0), (900, -900, "classified", 1000),
])
def test_upstream_threshold_and_clamp_are_independent_of_coach_quality(best_cp, played_cp, status, loss):
    stockfish = evidence(best_cp=best_cp, played_cp=played_cp)
    stockfish["move_quality"] = {"status": "good"}
    result = classify_review(chess.STARTING_FEN, "e2e4", stockfish)
    assert result.status == status
    assert result.cp_loss == loss
    assert result.threshold_cp == 200


@pytest.mark.parametrize("best_score,played_score,motif", [
    ({"cp": 0, "mate": None}, {"cp": None, "mate": -2}, "allowed_mate"),
    ({"cp": None, "mate": 3}, {"cp": 500, "mate": None}, "missed_mate"),
    ({"cp": None, "mate": 2}, {"cp": None, "mate": 3}, None),
    ({"cp": None, "mate": -4}, {"cp": None, "mate": -2}, None),
])
def test_mate_scores_convert_from_root_to_opponent_perspective(best_score, played_score, motif):
    stockfish = evidence()
    stockfish["top_moves"][0]["score"].update(best_score)
    stockfish["played_move"]["score"].update(played_score)
    result = classify_review(chess.STARTING_FEN, "e2e4", stockfish)
    assert result.motif == motif
    assert result.status != "unavailable"


def test_checkmate_is_not_missed_mate_and_needs_no_opponent_reply():
    fen = "7k/8/5KQ1/8/8/8/8/8 w - - 0 1"
    stockfish = evidence(fen, "g6g7", "g6g7", None)
    for move in [stockfish["top_moves"][0], stockfish["played_move"]]:
        move["score"].update(cp=None, mate=1)
    result = classify_review(fen, "g6g7", stockfish)
    assert result.status == "below_threshold"
    assert result.motif is None and result.cp_loss == 0


@pytest.mark.parametrize("change", [
    lambda s: s.update(perspective="Black"),
    lambda s: s.update(fen="another position"),
    lambda s: s.update(top_moves=[]),
    lambda s: s["top_moves"].append(deepcopy(s["top_moves"][0])),
    lambda s: s["played_move"].update(uci="a2a4"),
    lambda s: s["played_move"].update(depth=17),
    lambda s: s["played_move"]["score"].update(bound="lower"),
    lambda s: s["played_move"]["score"].update(cp=400),
    lambda s: s["played_move"].update(pv_uci=["e2e4"]),
    lambda s: s["played_move"].update(pv_uci=["e7e5"]),
    lambda s: s["played_move"].update(pv_uci=["e2e4", "e7e4"]),
    lambda s: s["top_moves"][0].pop("pv_uci"),
])
def test_incomplete_or_unreliable_evidence_is_not_a_negative_detection(change):
    stockfish = evidence()
    change(stockfish)
    result = classify_review(chess.STARTING_FEN, "e2e4", stockfish)
    assert result.status == "unavailable"
    assert result.motif is None and result.cp_loss is None


def test_no_recorded_move_and_legacy_missing_evidence():
    assert classify_review(chess.STARTING_FEN, None, None).label == "Unavailable — no recorded move"
    assert classify_review(chess.STARTING_FEN, "e2e4", None).status == "unavailable"


def test_response_and_saved_endpoint_only_add_display_metadata():
    fen = "r3k3/8/8/1N6/8/8/8/4K3 w - - 0 1"
    stockfish = evidence(fen, "b5c7", "e1d1", "a8a7")
    saved = {"fen": fen, "played_move": "e1d1", "stockfish": stockfish,
             "text": "The original coach response.", "model": "model", "response_id": "saved",
             "created_at": datetime.now(timezone.utc)}
    original = deepcopy(saved)
    app = FastAPI()
    app.state.db = Mock()
    app.state.db.coach_feedback_for_reviews.return_value = {(fen, "e1d1"): saved}
    factory = Mock(side_effect=AssertionError("Reading a label must not run the coach"))
    app.include_router(create_coach_router(factory))
    with TestClient(app) as client:
        response = client.get("/api/coach/feedback", params={"fen": fen, "played_move": "e1d1"})
    assert response.status_code == 200
    data = response.json()
    assert data["telemetry_classification"]["motif"] == "missed_fork"
    assert data["text"] == original["text"]
    assert data == AnalyzePositionResponse(**saved).model_dump(mode="json")
    assert saved == original
    app.state.db.save_coach_feedback.assert_not_called()
    factory.assert_not_called()
