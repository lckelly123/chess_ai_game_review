from copy import deepcopy
from unittest.mock import Mock

import chess
import chess.engine
import pytest

from backend.coach.move_quality import assess_move, analyze_played_move, prepare_position_evidence, _played_candidate
from backend.coach.player_move_quality import assess_player_move, PLAYER_QUALITY_POLICY
from backend.coach.move_review import MoveReview
from backend.coach.position_classification import analyze_position
from backend.coach.stockfish import StockfishSettings, StockfishUnavailableError
from backend.coach.teaching import TeachingOutput, TeachingAnalysis
from backend.coach.responses import build_request
from backend.tests.position_fixtures import position_evidence
from backend.tests.test_coach import teaching_output


def candidate(wins=600, draws=100, cp=100, depth=12):
    return {"wdl": {"wins": wins, "draws": draws, "losses": 1000-wins-draws},
            "score": {"cp": cp, "mate": None, "bound": "exact"}, "depth": depth}


@pytest.mark.parametrize("wins,expected", [(600, "acceptable"), (550, "acceptable"), (549, "meaningfully_inferior")])
def test_quality_uses_exact_expected_score_threshold(wins, expected):
    result = assess_move(candidate(), candidate(wins, cp=50))
    assert result["status"] == expected
    assert result["expected_score_loss_pp"] == pytest.approx((600-wins)/10)


def test_winning_alternative_is_not_penalized_for_large_cp_gap():
    assert assess_move(candidate(1000, 0, 1500), candidate(1000, 0, 700))["status"] == "acceptable"


@pytest.mark.parametrize("extra", [{}, {"wdl": chess.engine.PovWdl(chess.engine.Wdl(600, 100, 300), chess.WHITE), "upperbound": True}])
def test_played_root_without_reliable_quality_retains_observable_evidence(extra):
    info = {"pv": [chess.Move.from_uci("e2e4")], "score": chess.engine.PovScore(chess.engine.Cp(100), chess.WHITE),
            "depth": 12, **extra}
    played = _played_candidate(chess.Board(), info)
    assert played["uci"] == "e2e4" and played["pv_san"] == ["e4"]
    assert assess_move(candidate(), played)["status"] == "uncertain"


@pytest.mark.parametrize("changes", [
    {"depth": 11}, {"wdl": None}, {"wdl": {"wins": 1001, "draws": 0, "losses": -1}},
    {"score": {"cp": 120, "mate": None, "bound": "exact"}},
    {"score": {"cp": 10, "mate": None, "bound": "lower"}},
    {"wdl": {"wins": 700, "draws": 100, "losses": 200}},
])
def test_unreliable_or_conflicting_evidence_is_uncertain(changes):
    assert assess_move(candidate(), {**candidate(), **changes}) == {"status": "uncertain", "expected_score_loss_pp": None}


def test_position_pool_excludes_inferior_moves_without_changing_top_five_or_classification():
    original = position_evidence(chess.STARTING_FEN)
    original["top_moves"][-1].update(candidate(100, 100, -150))
    prepared = prepare_position_evidence(original)
    assert len(prepared["top_moves"]) == 5
    assert len(prepared["permitted_candidate_uci"]) == 4
    assert prepared["decision_classification"] == original["decision_classification"]
    assert original["top_moves"][-1]["quality"]["status"] == "acceptable"  # no mutation


def test_in_pool_played_moves_reuse_search_without_engine_process(monkeypatch):
    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", Mock(side_effect=AssertionError("No duplicate search")))
    original = position_evidence(chess.STARTING_FEN)
    snapshot = deepcopy(original)
    for move in original["top_moves"]:
        result = analyze_played_move(MoveReview.from_fen(chess.STARTING_FEN, move["uci"]), original)
        assert result["played_move_in_top"] and result["move_quality"]["status"] == "good"
        assert result["move_quality_policy"] == PLAYER_QUALITY_POLICY
        assert result["played_move"]["uci"] == move["uci"]
    assert original == snapshot


def test_changing_played_move_keeps_position_request_evidence_identical():
    evidence = position_evidence(chess.STARTING_FEN)
    messages = [build_request(chess.STARTING_FEN, evidence=evidence, played_move=move["uci"])["input"][1]["content"]
                for move in evidence["top_moves"][:2]]
    position_parts = [message.split("Player-move information", 1)[0] for message in messages]
    assert position_parts[0] == position_parts[1]
    assert messages[0] != messages[1]


def test_outside_pool_search_stays_on_original_board_and_perspective(monkeypatch):
    board = chess.Board()
    board.push_uci("e2e4")
    position = position_evidence(board.fen())
    played = chess.Move.from_uci("e7e5")
    engine = Mock()
    engine.__enter__ = Mock(return_value=engine)
    engine.__exit__ = Mock(return_value=False)
    engine.id = {"name": "Test Stockfish"}
    engine.options = {"UCI_ShowWDL": True}
    engine.analyse.return_value = {"pv": [played], "depth": 12,
        "score": chess.engine.PovScore(chess.engine.Cp(-50), chess.WHITE),
        "wdl": chess.engine.PovWdl(chess.engine.Wdl(350, 100, 550), chess.WHITE)}
    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", lambda *args, **kwargs: engine)
    monkeypatch.setattr(StockfishSettings, "executable", lambda self: "stockfish")
    result = analyze_played_move(MoveReview.from_fen(board.fen(), "e7e5"), position)
    args, kwargs = engine.analyse.call_args
    assert args[0].fen() == board.fen() and args[1].depth == 12
    assert kwargs == {"root_moves": [played]}
    assert result["perspective"] == "Black" and result["played_move"]["score"]["cp"] == 50
    assert result["move_quality"] == assess_player_move(position["top_moves"][0], result["played_move"])
    assert result["move_quality"]["status"] == "good"
    assert not result["played_move_in_top"]
    engine.__exit__.assert_called_once()


def test_feedback_reuses_reason_only_for_acceptable_selected_move():
    data = teaching_output()
    data["move_evaluation"] = {"plan_alignment": "aligned", "explanation": None, "better_candidate_uci": None}
    teaching = TeachingOutput.model_validate(data)
    evidence = {"move_quality": {"status": "good"}}
    teaching.validate_move_evaluation(played_move="g1h3", evidence=evidence)
    teaching.move_evaluation.explanation = "A duplicate reason."
    with pytest.raises(ValueError):
        teaching.validate_move_evaluation(played_move="g1h3", evidence=evidence)
    teaching.move_evaluation.explanation = None
    for move, quality in [("e2e4", "good"), ("g1h3", "uncertain"), ("g1h3", "inaccuracy"), (None, "good")]:
        with pytest.raises(ValueError):
            teaching.validate_move_evaluation(played_move=move, evidence={"move_quality": {"status": quality}})


def test_better_move_reference_requires_selected_candidate_and_meaningful_improvement():
    data = teaching_output()
    data["move_evaluation"] = {"plan_alignment": "aligned", "explanation": "The idea is useful, but the execution loses material.", "better_candidate_uci": "g1h3"}
    teaching = TeachingOutput.model_validate(data)
    evidence = {"move_quality": {"status": "inaccuracy"}, "top_moves": [{"uci": "g1h3", **candidate()}],
                "played_move": {"uci": "e2e4", **candidate(500, 100, 0)}}
    teaching.validate_move_evaluation(played_move="e2e4", evidence=evidence)
    evidence["played_move"].update(candidate(550, 100, 50))
    with pytest.raises(ValueError):
        teaching.validate_move_evaluation(played_move="e2e4", evidence=evidence)
    evidence["played_move"].update(candidate(500, 100, 0))
    teaching.move_evaluation.better_candidate_uci = "d2d4"
    with pytest.raises(ValueError):
        teaching.validate_move_evaluation(played_move="e2e4", evidence=evidence)


def test_old_saved_three_field_output_still_loads_but_new_outputs_require_four():
    old = teaching_output()
    del old["move_evaluation"]
    assert TeachingAnalysis.model_validate(old).move_evaluation is None
    with pytest.raises(ValueError):
        TeachingOutput.model_validate(old)


def test_real_stockfish_missing_played_move_has_wdl_from_same_root():
    settings = StockfishSettings(depth=4, time_limit=2, threads=1, hash_mb=16)
    try:
        settings.executable()
    except StockfishUnavailableError:
        pytest.skip("Install Stockfish for the native engine smoke test.")
    position = prepare_position_evidence(analyze_position(chess.STARTING_FEN, settings))
    roots = {move["uci"] for move in position["top_moves"]}
    played = next(move.uci() for move in chess.Board().legal_moves if move.uci() not in roots)
    result = analyze_played_move(MoveReview.from_fen(chess.STARTING_FEN, played), position, settings)
    assert result["played_move"]["uci"] == played and not result["played_move_in_top"]
    assert sum(result["played_move"]["wdl"].values()) == 1000
    assert result["played_move"]["depth"] == position["top_moves"][0]["depth"]
    assert result["perspective"] == "White"
