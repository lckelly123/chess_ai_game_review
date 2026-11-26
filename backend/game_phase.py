"""Lichess/scalachess Divider.scala phase rules, including piece mixedness.

Source: https://github.com/lichess-org/scalachess/blob/master/core/src/main/scala/Divider.scala
"""
import chess


def _region_score(y: int, white: int, black: int) -> int:
    if white == 0:
        return {1: 1 + y, 2: 8 - y if y < 6 else 0,
                3: 10 - y if y < 7 else 0, 4: 10 - y if y < 7 else 0}.get(black, 0)
    if white == 1:
        return {0: 9 - y, 1: 5 + abs(4 - y), 2: 11 - y, 3: 12 - y}.get(black, 0)
    if white == 2:
        return {0: y if y > 2 else 0, 1: 3 + y, 2: 7}.get(black, 0)
    if white == 3:
        return {0: 2 + y if y > 1 else 0, 1: 4 + y}.get(black, 0)
    return 2 + y if white == 4 and black == 0 and y > 1 else 0


def mixedness(board: chess.Board) -> int:
    return sum(_region_score(y + 1, (board.occupied_co[chess.WHITE] & region).bit_count(),
                             (board.occupied_co[chess.BLACK] & region).bit_count())
               for y in range(7) for x in range(7) for region in [0x0303 << (x + 8 * y)])


def next_phase(board: chess.Board, previous: str = "opening") -> str:
    pieces = (board.occupied & ~(board.kings | board.pawns)).bit_count()
    if previous == "endgame" or pieces <= 6:
        return "endgame"
    if (previous == "middlegame" or pieces <= 10
            or (board.occupied_co[chess.WHITE] & chess.BB_RANK_1).bit_count() < 4
            or (board.occupied_co[chess.BLACK] & chess.BB_RANK_8).bit_count() < 4
            or mixedness(board) > 150):
        return "middlegame"
    return "opening"
