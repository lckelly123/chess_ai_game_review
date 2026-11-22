"""Versioned, deterministic position sharpness from five root engine scores."""

import math

import chess

SHARPNESS_VERSION = 2
CAP_CP = 1000
A_CP = 10
CUTOFF_CP = 687.68
WEIGHTS = tuple(math.exp(-i) / sum(math.exp(-j) for j in range(4)) for i in range(4))
TAGS = ((20, "forgiving"), (40, "flexible"), (60, "selective"), (80, "demanding"), (100, "critical"))


def normalized_sharpness(raw_cp: float) -> float:
    if not math.isfinite(raw_cp) or raw_cp < 0:
        raise ValueError("Sharpness must be finite and nonnegative.")
    return 100 * min(1, math.log1p(raw_cp / A_CP) / math.log1p(CUTOFF_CP / A_CP))


def sharpness_tag(score: float) -> str:
    if not math.isfinite(score) or not 0 <= score <= 100:
        raise ValueError("Normalized sharpness must be between 0 and 100.")
    return next(tag for ceiling, tag in TAGS if score <= ceiling)


def with_position_sharpness(evidence: dict, *, expected_fen: str | None = None) -> dict:
    """Recompute from raw evidence without changing engine scores or their ranks.

    This is also the read adapter for legacy saves. Missing or invalid five-move
    evidence stays explicitly unclassified; a cached label is never trusted.
    """
    sharpness = {"version": SHARPNESS_VERSION, "raw_cp": None, "score": None,
                 "cap_cp": CAP_CP, "a_cp": A_CP, "cutoff_cp": CUTOFF_CP,
                 "lambda": 1, "weights": list(WEIGHTS), "capped_scores_cp": None}
    result = {**evidence, "sharpness": sharpness, "classification": None,
              "decision_classification": None, "unclassified_reason": "insufficient_engine_evidence"}
    try:
        board = chess.Board(evidence["fen"])
        if not board.is_valid() or evidence.get("perspective") != ("White" if board.turn else "Black"):
            return result
        if expected_fen is not None and board.fen(en_passant="fen") != chess.Board(expected_fen).fen(en_passant="fen"):
            return result
        legal_count = board.legal_moves.count()
        result["legal_move_count"] = legal_count
        if board.is_game_over():
            return {**result, "unclassified_reason": "terminal_position"}
        if legal_count < 5:
            reason = "single_legal_move" if legal_count == 1 else "fewer_than_five_legal_moves"
            return {**result, "unclassified_reason": reason}
        candidates = evidence["top_moves"]
        if (len(candidates) != 5 or len({c["uci"] for c in candidates}) != 5
                or {c["rank"] for c in candidates} != set(range(1, 6))
                or len({c["depth"] for c in candidates}) != 1):
            return result
        scores = []
        for candidate in candidates:
            if (type(candidate["depth"]) is not int or candidate["depth"] < 1
                    or chess.Move.from_uci(candidate["uci"]) not in board.legal_moves):
                return result
            score = candidate["score"]
            cp, mate = score.get("cp"), score.get("mate")
            if score.get("bound") != "exact" or (cp is None) == (mate is None):
                return result
            if mate is not None:
                if type(mate) is not int or mate == 0:
                    return result
                scores.append(CAP_CP if mate > 0 else -CAP_CP)
            else:
                if type(cp) is not int:
                    return result
                scores.append(max(-CAP_CP, min(CAP_CP, cp)))
        scores.sort(reverse=True)
        raw = sum(w * (scores[i] - scores[i+1]) for i, w in enumerate(WEIGHTS))
        normalized = normalized_sharpness(raw)
        tag = sharpness_tag(normalized)
        sharpness.update(raw_cp=raw, score=normalized, capped_scores_cp=scores)
        return {**result, "classification": tag.title(), "decision_classification": tag,
                "unclassified_reason": None}
    except (KeyError, TypeError, ValueError, AttributeError):
        return result
