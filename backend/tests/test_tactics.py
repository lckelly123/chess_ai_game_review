from copy import deepcopy
from unittest.mock import Mock

import chess
import pytest

from backend.coach.move_review import MoveReview
from backend.coach.stockfish import StockfishSettings
from backend.tactics.classification import (
    EXTENSION_NODES, MAX_PLIES, _extend, classify_review, detect_motifs, with_tactic_classification,
)

FORK = "3q1k2/8/8/6N1/8/8/P7/6K1 w - - 0 1"


def moves(line):
    return [chess.Move.from_uci(value) for value in line.split()]


def evidence(fen=FORK, best="g5e6 f8e8 e6d8", played="g1h1 d8g5 h1h2 f8e8"):
    board = chess.Board(fen)
    def candidate(line, rank, cp):
        sequence = moves(line)
        replay = board.copy()
        for move in sequence:
            assert move in replay.legal_moves
            replay.push(move)
        return {"uci": sequence[0].uci(), "pv_uci": [m.uci() for m in sequence], "rank": rank,
                "depth": 18, "score": {"cp": cp, "mate": None, "bound": "exact"}}
    return {"fen": fen, "perspective": "White" if board.turn else "Black",
            "top_moves": [candidate(best, 1, 500)], "played_move": candidate(played, None, -300)}


@pytest.mark.parametrize("fen,line,expected", [
    (FORK, "g5e6", "fork"),  # Last available actor move is deliberately inspected.
    ("7k/8/8/4q3/8/8/8/4R1K1 w - - 0 1", "e1e5", "hanging_piece"),
    ("7k/6r1/8/4q3/8/8/1B6/K7 w - - 0 1", "b2c3 e5f5 c3g7", "skewer"),
    ("4k3/8/8/8/8/8/4B3/4R1K1 w - - 0 1", "e2d3", "discovered_attack"),
    ("4k3/8/8/8/8/8/4B3/4R1K1 w - - 0 1", "e2b5", "double_check"),
    ("4k3/4q3/8/8/8/8/8/4R1K1 w - - 0 1", "e1e2", "pin"),
])
def test_real_legal_motif_sequences_for_both_colors(fen, line, expected):
    board, sequence = chess.Board(fen), moves(line)
    replay = board.copy()
    for move in sequence:
        assert move in replay.legal_moves
        replay.push(move)
    snapshot = board.fen()
    assert expected in detect_motifs(board, sequence)
    assert board.fen() == snapshot
    mirrored = [chess.Move(chess.square_mirror(m.from_square), chess.square_mirror(m.to_square),
                           promotion=m.promotion) for m in sequence]
    assert expected in detect_motifs(board.mirror(), mirrored)


def test_both_missed_and_allowed_findings_are_retained_without_mutation():
    source = evidence()
    original = deepcopy(source)
    result = with_tactic_classification(FORK, "g1h1", source, allow_engine=False)
    tags = result["tactic_classification"]
    assert tags["status"] == "classified"
    missed, allowed = tags["lines"]
    assert missed["direction"] == "missed" and missed["side"] == "white"
    assert "fork" in missed["motifs"]
    assert allowed["direction"] == "allowed" and allowed["side"] == "black"
    assert "hanging_piece" in allowed["motifs"]
    assert allowed["line_uci"][0] == "d8g5"  # Setup move is not attributed to Black.
    assert source == original


@pytest.mark.parametrize("cp,expected", [(450, "not_applicable"), (400, "classified"),
                                         (300, "classified"), (-300, "classified")])
def test_eligibility_uses_existing_player_quality_not_a_new_cp_threshold(cp, expected):
    source = evidence()
    source["top_moves"][0]["score"]["cp"] = 100
    source["played_move"]["score"]["cp"] = {450: 90, 400: 30, 300: -30, -300: -300}[cp]
    forbidden = Mock(side_effect=AssertionError("No extension expected"))
    result = classify_review(FORK, "g1h1", source, extend=forbidden)
    assert result["status"] == expected
    forbidden.assert_not_called()


@pytest.mark.parametrize("change", ["perspective", "fen", "depth", "bound", "illegal_pv", "missing_pv"])
def test_invalid_evidence_does_not_become_no_tactic(change):
    source = evidence()
    if change == "perspective": source["perspective"] = "Black"
    elif change == "fen": source["fen"] = chess.STARTING_FEN
    elif change == "depth": source["played_move"]["depth"] = 17
    elif change == "bound": source["played_move"]["score"]["bound"] = "lower"
    else:
        for candidate in [*source["top_moves"], source["played_move"]]:
            candidate["pv_uci"] = [candidate["uci"], "a1a8"] if change == "illegal_pv" else []
    extension = Mock(side_effect=AssertionError("Do not extend untrusted lines"))
    result = classify_review(FORK, "g1h1", source, allow_engine=True, extend=extension)
    assert result["status"] == "insufficient_evidence"
    extension.assert_not_called()


def test_short_quiet_lines_stay_insufficient_and_never_positional():
    source = evidence(chess.STARTING_FEN, "e2e4 e7e5", "d2d4 d7d5")
    result = classify_review(chess.STARTING_FEN, "d2d4", source)
    assert result["status"] == "insufficient_evidence"
    assert not any(line["motifs"] for line in result["lines"])


def test_ingestion_extends_two_branches_once_and_keeps_root_evidence():
    source = evidence()
    original = deepcopy(source)
    calls = []
    def extend(board, prefix, settings):
        calls.append((board.fen(), [m.uci() for m in prefix]))
        replay = board.copy()
        for move in prefix: replay.push(move)
        sequence = list(prefix)
        while len(sequence) < MAX_PLIES and not replay.is_game_over():
            move = next(iter(replay.legal_moves))
            sequence.append(move)
            replay.push(move)
        return sequence
    result = classify_review(FORK, "g1h1", source, settings=StockfishSettings(),
                             allow_engine=True, extend=extend)
    assert len(calls) == 2
    after = chess.Board(FORK)
    after.push_uci("g1h1")
    assert calls[0][0] == FORK and calls[1][0] == after.fen()
    assert all(line["extended"] for line in result["lines"])
    assert source == original


def test_extension_failure_retains_observed_findings_as_partial():
    result = classify_review(FORK, "g1h1", evidence(), allow_engine=True,
                             extend=Mock(side_effect=TimeoutError()))
    assert result["status"] == "classified"
    assert all(line["coverage"] == "insufficient" and line["reason"] == "extension_unavailable"
               for line in result["lines"])


def test_played_move_analysis_attaches_classification_before_persistence(monkeypatch):
    from backend.coach.move_quality import analyze_played_move
    source = evidence()
    position = {**source, "engine": "Fixture", "top_moves": [*source["top_moves"], source["played_move"]]}
    monkeypatch.setattr("backend.coach.move_quality.with_tactic_classification",
                        lambda fen, played, result, **kwargs: with_tactic_classification(fen, played, result, allow_engine=False))
    result = analyze_played_move(MoveReview.from_fen(FORK, "g1h1"), position)
    assert result["tactic_classification"]["status"] == "classified"
    assert result["played_move"]["score"] == source["played_move"]["score"]


def test_response_serialization_never_runs_tactic_searches():
    from datetime import datetime, timezone
    from backend.coach.routes import AnalyzePositionResponse
    cached = with_tactic_classification(FORK, "g1h1", evidence(), allow_engine=False)
    response = AnalyzePositionResponse(fen=FORK, played_move="g1h1", text="Saved review", model="test",
                                       response_id="test", created_at=datetime.now(timezone.utc), stockfish=cached)
    assert response.model_dump()["stockfish"]["tactic_classification"] == cached["tactic_classification"]


def test_tactic_findings_are_not_sent_to_coach():
    from backend.coach.responses import build_request
    from backend.tests.position_fixtures import position_evidence
    data = build_request(chess.STARTING_FEN, evidence=position_evidence(chess.STARTING_FEN), played_move="g1h3")
    assert "tactic_classification" not in data["input"][1]["content"]


def test_extension_uses_leaf_and_hard_resource_limits(monkeypatch):
    board = chess.Board()
    prefix = moves("e2e4 e7e5")
    engine = Mock()
    searched_fens = []
    def analyse(leaf, limit):
        searched_fens.append(leaf.fen())
        return {"pv": moves("g1f3 b8c6")}
    engine.analyse.side_effect = analyse
    context = Mock()
    context.__enter__ = Mock(return_value=engine)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(StockfishSettings, "executable", lambda _: "stockfish")
    monkeypatch.setattr("chess.engine.SimpleEngine.popen_uci", lambda *args, **kwargs: context)
    extended = _extend(board, prefix, StockfishSettings(depth=16, time_limit=10))
    _, limit = engine.analyse.call_args.args
    expected_leaf = board.copy()
    for move in prefix:
        expected_leaf.push(move)
    assert searched_fens == [expected_leaf.fen()]
    assert limit.time == 2 and limit.nodes == EXTENSION_NODES and limit.depth == 16
    assert [move.uci() for move in extended] == ["e2e4", "e7e5", "g1f3", "b8c6"]
    assert board.fen() == chess.STARTING_FEN


def test_real_stockfish_extends_both_directions():
    from backend.coach.stockfish import StockfishUnavailableError
    settings = StockfishSettings(depth=10, time_limit=1, threads=1, hash_mb=16)
    try:
        settings.executable()
    except StockfishUnavailableError:
        pytest.skip("Install Stockfish for the native engine smoke test.")
    result = classify_review(FORK, "g1h1", evidence(), settings=settings, allow_engine=True)
    assert result["status"] == "classified"
    assert all(line["extended"] for line in result["lines"])
    assert all(len(line["line_uci"]) <= MAX_PLIES for line in result["lines"])
    assert "fork" in result["lines"][0]["motifs"]
