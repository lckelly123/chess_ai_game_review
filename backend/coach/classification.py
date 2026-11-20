"""Classification metadata and facts derived from the original engine position."""

import chess

CLASSIFICATION_VERSION = 2


def current_classification(review: dict | None) -> bool:
    """An explicit null is a completed classification; an old review is not."""
    if not review or review.get("classification_version") != CLASSIFICATION_VERSION:
        return False
    teaching = review.get("teaching") or {}
    evaluation = teaching.get("move_evaluation") or {}
    return "mistake_classification" in evaluation


def best_move_piece(fen: str, evidence: dict | None) -> str | None:
    """Use rank 1, never instructional candidate order or the played piece."""
    if not evidence or evidence.get("fen") != fen:
        return None
    try:
        board = chess.Board(fen)
        if evidence.get("perspective") != ("White" if board.turn else "Black"):
            return None
        leaders = [move for move in evidence.get("top_moves", []) if move.get("rank") == 1]
        if len(leaders) != 1:
            return None
        leader = leaders[0]
        if leader.get("depth", 0) < 1 or leader.get("score", {}).get("bound") != "exact":
            return None
        move = chess.Move.from_uci(leader["uci"])
        if move not in board.legal_moves:
            return None
        return chess.piece_name(board.piece_type_at(move.from_square))
    except (ValueError, KeyError, TypeError):
        return None
