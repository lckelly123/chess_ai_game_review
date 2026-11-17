"""Validated, pre-move inputs for the second coaching pass."""

import hashlib
from dataclasses import dataclass

import chess

from ..chess_games import replay
from .position import CoachPosition, InvalidPositionError


class NoPlayedMoveError(ValueError):
    pass


@dataclass(frozen=True)
class MoveReview:
    position: CoachPosition
    played_move_uci: str
    played_move_san: str

    @classmethod
    def from_fen(cls, fen: str, played_move: str) -> "MoveReview":
        position = CoachPosition.from_fen(fen)
        board = chess.Board(position.fen)
        try:
            move = chess.Move.from_uci(played_move)
        except (ValueError, TypeError) as exc:
            raise InvalidPositionError("Supply the played move in UCI notation, such as e2e4 or a7a8q.") from exc
        if move not in board.legal_moves:
            raise InvalidPositionError("The played move is not legal in the supplied pre-move position.")
        return cls(position, move.uci(), board.san(move))

    @classmethod
    def from_game(cls, pgn: str, ply: int) -> "MoveReview":
        """ply is the number of moves already played, as in the replay slider."""
        detail = replay(pgn)
        if type(ply) is not int or not 0 <= ply < len(detail["positions"]):
            raise InvalidPositionError("The selected replay position is outside this game.")
        if ply == len(detail["moves"]):
            raise NoPlayedMoveError("There is no next recorded move at the final position.")
        return cls.from_fen(detail["positions"][ply]["fen"], detail["moves"][ply]["uci"])

    @property
    def review_key(self) -> str:
        # Position-only coaching keeps its FEN identity. Move feedback needs a
        # distinct identity for each played move from the same position.
        return hashlib.sha256(f"{self.position.fen}\n{self.played_move_uci}".encode()).hexdigest()

    def as_dict(self) -> dict:
        return {
            "review_key": self.review_key,
            "fen": self.position.fen,
            "ascii_board": self.position.ascii_board,
            "side_to_move": self.position.side_to_move,
            "played_move": {"uci": self.played_move_uci, "san": self.played_move_san},
        }
