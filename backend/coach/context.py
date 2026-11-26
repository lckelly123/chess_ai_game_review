"""Validated previous-move context and versioned coaching identity."""

import hashlib

import chess

from .position import CoachPosition, InvalidPositionError

# Independent of mistake taxonomy and sharpness versions. Values through 3
# were used by the former classification-based game coaching progress marker.
COACH_CONTRACT_VERSION = 5


def validate_previous_move(fen: str, previous_move: dict | None) -> dict | None:
    if previous_move is None:
        return None
    try:
        before = CoachPosition.from_fen(previous_move["fen"])
        board = chess.Board(before.fen)
        move = chess.Move.from_uci(previous_move["uci"])
        if move not in board.legal_moves:
            raise ValueError("Illegal previous move")
        san = board.san(move)
        board.push(move)
        # Normalize uncapturable en-passant targets, as PGN replay does.
        if board.fen() != chess.Board(fen).fen():
            raise ValueError("Previous move does not lead to this position")
        return {"fen": chess.Board(before.fen).fen(), "uci": move.uci(), "san": san}
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidPositionError("Previous-move context must legally lead to the selected position.") from exc


def previous_move_from_replay(detail: dict, ply: int) -> dict | None:
    if ply == 0:
        return None
    return validate_previous_move(detail["positions"][ply]["fen"], {
        "fen": detail["positions"][ply - 1]["fen"], "uci": detail["moves"][ply - 1]["uci"],
    })


def context_key(previous_move: dict | None) -> str:
    if previous_move is None:
        return ""
    return hashlib.sha256(f"{previous_move['fen']}\n{previous_move['uci']}".encode()).hexdigest()


def current_coaching(review: dict | None) -> bool:
    from .classification import current_classification
    return bool(review and review.get("coach_contract_version") == COACH_CONTRACT_VERSION
                and current_classification(review))
