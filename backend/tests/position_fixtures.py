"""Deterministic first-pass engine evidence for mocked coaching tests."""

import chess

from backend.coach.position import CoachPosition


def position_evidence(fen, *, preferred=()):
    position = CoachPosition.from_fen(fen)
    board = chess.Board(position.fen)
    legal = list(board.legal_moves)
    moves = [] if board.is_game_over() else list(dict.fromkeys([chess.Move.from_uci(uci) for uci in preferred] + legal))[:5]
    candidates = []
    for index, move in enumerate(moves):
        candidates.append({
            "rank": index + 1, "uci": move.uci(), "san": board.san(move), "depth": 12,
            "score": {"cp": 100 - 10 * index, "mate": None, "bound": "exact"},
            "pv_uci": [move.uci()], "pv_san": [board.san(move)],
            "wdl": {"wins": 600 - 10 * index, "draws": 100, "losses": 300 + 10 * index},
            "probabilities": {"win": .6 - .01 * index, "draw": .1, "loss": .3 + .01 * index},
            "expected_score": .65 - .01 * index,
            "relative_quality": {"cp_loss_from_best": 10 * index, "expected_score_loss_pp": index},
        })
    return {
        "fen": position.fen, "perspective": position.side_to_move, "engine": "Stockfish position test",
        "classification": "Flexible" if len(moves) > 1 else None,
        "decision_classification": "flexible" if len(moves) > 1 else None,
        "unclassified_reason": "terminal_position" if not moves else "single_legal_move" if len(moves) == 1 else None,
        "delta_cp": 10 if len(moves) > 1 else None, "delta_e_pp": 1 if len(moves) > 1 else None,
        "legal_move_count": len(legal), "top_moves": candidates,
        "position_outlook": {key: candidates[0][key] for key in ("score", "wdl", "probabilities", "expected_score")} if candidates else None,
        "permitted_candidate_uci": [move.uci() for move in moves],
    }
