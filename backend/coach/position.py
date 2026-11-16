"""Validate a selected position and derive its model-facing representation."""

from dataclasses import dataclass

import chess


class InvalidPositionError(ValueError):
    """The FEN is invalid, or its supplied ASCII representation disagrees."""


@dataclass(frozen=True)
class CoachPosition:
    fen: str
    ascii_board: str
    side_to_move: str

    @classmethod
    def from_fen(cls, fen: str, *, ascii_board: str | None = None) -> "CoachPosition":
        if not isinstance(fen, str) or len(fen.split()) != 6:
            raise InvalidPositionError("Supply a complete six-field FEN, including the side to move.")
        try:
            board = chess.Board(fen)
        except ValueError as exc:
            raise InvalidPositionError("The FEN could not be parsed as a standard chess position.") from exc
        if not board.is_valid():
            raise InvalidPositionError("The FEN describes an invalid standard chess position.")

        # Fixed White-at-bottom orientation, independent of the UI's board flip.
        rows = str(board).splitlines()
        diagram = "\n".join(f"{8 - index}  {row}" for index, row in enumerate(rows))
        diagram += "\n\n   a b c d e f g h"
        if ascii_board is not None:
            if not isinstance(ascii_board, str) or ascii_board.split() not in (diagram.split(), str(board).split()):
                raise InvalidPositionError("The ASCII board must match the FEN, with rank 8 first and White at the bottom.")

        # Preserve the FEN en-passant target even when no legal capture exists.
        return cls(board.fen(en_passant="fen"), diagram, "White" if board.turn else "Black")

    def as_user_message(self) -> str:
        return (
            f"Analyze this selected position for {self.side_to_move}, the side to move.\n\n"
            f"FEN:\n{self.fen}\n\n"
            "ASCII board (rank 8 at the top; uppercase = White, lowercase = Black, . = empty):\n"
            f"{self.ascii_board}"
        )
