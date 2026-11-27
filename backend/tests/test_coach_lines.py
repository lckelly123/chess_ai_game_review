import chess
import pytest

from backend.coach.lines import candidate_positions, move_lines
from backend.coach.routes import AnalyzePositionResponse
from backend.tests.test_coach import teaching_output


@pytest.mark.parametrize("fen,pv", [
    (chess.STARTING_FEN, ["e2e4", "e7e5", "g1f3"]),
    ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", ["e1g1", "e8c8"]),
    ("7k/P7/8/8/8/8/8/7K w - - 0 1", ["a7a8n"]),
    ("7k/8/8/3pP3/8/8/8/K7 w - d6 0 2", ["e5d6"]),
    ("7k/8/6QK/8/8/8/8/8 w - - 0 1", ["g6g7"]),
])
def test_line_playback_uses_the_original_position_and_handles_special_moves(fen, pv):
    line = move_lines(fen, {pv[0]: {"pv_uci": pv}})[pv[0]]
    assert candidate_positions(fen, [pv[0]])[pv[0]] == line["positions"][1]
    board = chess.Board(fen)
    assert line["positions"][0]["fen"] == fen
    for index, uci in enumerate(pv):
        move = chess.Move.from_uci(uci)
        assert line["san"][index] == board.san(move)
        board.push(move)
        position = line["positions"][index + 1]
        assert position["fen"] == board.fen(en_passant="fen")
        assert position["last_move"] == [uci[:2], uci[2:4]]
        assert position["check_square"] == (chess.square_name(board.king(board.turn)) if board.is_check() else None)


def test_missing_mismatched_and_invalid_lines_never_invent_a_continuation():
    assert candidate_positions(chess.STARTING_FEN, ["e2e5", "bad"]) == {}
    assert move_lines(chess.STARTING_FEN, {"e2e4": {}}) == {}
    assert move_lines(chess.STARTING_FEN, {"e2e4": {"pv_uci": ["d2d4"]}}) == {}
    assert move_lines(chess.STARTING_FEN, {"e2e4": {"pv_uci": "e2e4"}}) == {}
    for invalid in ["e2e3", "bad", None]:
        result = move_lines(chess.STARTING_FEN, {"e2e4": {"pv_uci": ["e2e4", invalid]}})
        assert result["e2e4"]["san"] == ["e4"]


def test_api_lines_include_only_selected_candidates_and_original_move_with_original_evidence_priority():
    response = AnalyzePositionResponse(
        fen=chess.STARTING_FEN, played_move="e2e4", text="Test", model="test", response_id="test", created_at="2026-11-25T00:00:00Z",
        teaching=teaching_output(),
        position_evidence={"top_moves": [
            {"uci": "g1h3", "pv_uci": ["g1h3", "e7e5"]},
            {"uci": "d2d4", "pv_uci": ["d2d4", "d7d5"]},
        ]},
        stockfish={"perspective": "White", "played_move": {"uci": "e2e4", "pv_uci": ["e2e4", "e7e5"]},
                   "top_moves": [{"uci": "e2e4", "pv_uci": ["e2e4", "d7d5"]}]},
    )
    assert set(response.move_lines) == {"g1h3", "e2e4"}
    assert response.move_lines["e2e4"]["san"] == ["e4", "e5"]


def test_saved_candidates_without_engine_lines_still_have_exact_preview_positions():
    response = AnalyzePositionResponse(
        fen=chess.STARTING_FEN, text="Test", model="test", response_id="test", created_at="2026-11-25T00:00:00Z",
        teaching=teaching_output(candidate_ucis=["e2e4"]),
    )
    assert response.move_lines == {}
    board = chess.Board()
    board.push_uci("e2e4")
    assert response.candidate_positions["e2e4"]["fen"] == board.fen(en_passant="fen")


def test_engine_only_reviews_expose_preview_positions_for_both_players_without_mutation():
    from copy import deepcopy
    from backend.game_analysis import analysis_result

    review = {"fen": chess.STARTING_FEN, "played_move": "d2d4",
              "stockfish": {"top_moves": [{"uci": "e2e4"}], "played_move": {"uci": "d2d4"}}}
    row = {"game_id": "test", "player_color": "white", "status": "completed", "total": 1, "completed": 1,
           "counts": {}, "error": None, "updated_at": "now", "moves": {"0": review}, "opponent_moves": {"1": review}}
    original = deepcopy(row)
    result = analysis_result(row)
    for section in ("moves", "opponent_moves"):
        saved = next(iter(result[section].values()))
        assert saved["candidate_positions"] == candidate_positions(chess.STARTING_FEN, ["e2e4"])
    assert row == original
