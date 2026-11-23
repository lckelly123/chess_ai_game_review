"""Classification metadata and facts derived from the original engine position."""

import chess

CLASSIFICATION_VERSION = 3


def current_classification(review: dict | None) -> bool:
    """Only reuse coaching generated under the current output contract."""
    if not review or review.get("classification_version") != CLASSIFICATION_VERSION:
        return False
    return lesson_classification(review)


def lesson_classification(review: dict | None) -> bool:
    """Version 2 and 3 saved labels share the same Lessons taxonomy."""
    if not review or review.get("classification_version") not in (2, CLASSIFICATION_VERSION):
        return False
    teaching = review.get("teaching") or {}
    evaluation = teaching.get("move_evaluation") or {}
    return "mistake_classification" in evaluation


def _best_move(fen: str, evidence: dict | None) -> chess.Move | None:
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
        return move
    except (ValueError, KeyError, TypeError):
        return None


def best_move_piece(fen: str, evidence: dict | None) -> str | None:
    move = _best_move(fen, evidence)
    return chess.piece_name(chess.Board(fen).piece_type_at(move.from_square)) if move else None


def positional_details(fen: str, played_move: str | None, evidence: dict | None) -> dict:
    """Identify both pieces at the original root; piece identity is its square."""
    best = _best_move(fen, evidence)
    if best is None:
        raise ValueError("Positional classification requires a reliable top-ranked engine move.")
    board = chess.Board(fen)
    played = chess.Move.from_uci(played_move) if played_move else None
    if played is None or played not in board.legal_moves:
        raise ValueError("Positional classification requires a legal recorded move.")
    return {
        "best_move_piece": chess.piece_name(board.piece_type_at(best.from_square)),
        "played_piece": chess.piece_name(board.piece_type_at(played.from_square)),
        "same_piece": best.from_square == played.from_square,
    }
