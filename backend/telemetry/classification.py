"""Adapt saved root-search evidence without running engines or changing coaching."""

from typing import Literal

import chess
from pydantic import BaseModel

from . import motifs

SOURCE_REVISION = "186ad9c61b770daf9c1778600a6a443be4ce3366"
MOTIF_MIN_CPL = 200
MATE_CLAMP = 1000
LABELS = {
    "hung_piece": "Hanging piece",
    "allowed_fork": "Allowed fork",
    "allowed_pin": "Allowed pin",
    "allowed_skewer": "Allowed skewer",
    "allowed_discovered": "Allowed discovered attack",
    "allowed_mate": "Allowed mate",
    "missed_capture": "Missed capture",
    "missed_fork": "Missed fork",
    "missed_pin": "Missed pin",
    "missed_skewer": "Missed skewer",
    "missed_discovered": "Missed discovered attack",
    "missed_mate": "Missed mate",
    "endgame_technique": "Endgame technique",
    "other": "Other (no recognized motif)",
}


class TelemetryClassification(BaseModel):
    status: Literal["classified", "below_threshold", "unavailable"]
    label: str
    motif: str | None = None
    cp_loss: int | None = None
    threshold_cp: int = MOTIF_MIN_CPL
    source_revision: str = SOURCE_REVISION


def _score(candidate: dict) -> dict:
    score = candidate.get("score")
    if not isinstance(score, dict) or score.get("bound") != "exact":
        raise ValueError("Missing exact score")
    cp, mate = score.get("cp"), score.get("mate")
    if not ((type(cp) is int and mate is None) or (cp is None and type(mate) is int and mate != 0)):
        # A pre-move search with a legal move cannot already be checkmated.
        raise ValueError("Invalid root score")
    return {"cp": cp, "mate": mate}


def _ordered_score(score: dict) -> tuple:
    mate = score["mate"]
    if mate is not None:
        return (2, -mate) if mate > 0 else (0, -mate)
    return (1, score["cp"])


def _clamped_cp(score: dict) -> int:
    if score["mate"] is not None:
        return MATE_CLAMP if score["mate"] > 0 else -MATE_CLAMP
    return max(-MATE_CLAMP, min(MATE_CLAMP, score["cp"]))


def _pv(board: chess.Board, candidate: dict) -> list[str]:
    line = candidate.get("pv_uci")
    if not isinstance(line, list) or not line or line[0] != candidate.get("uci"):
        raise ValueError("Missing root variation")
    replay = board.copy(stack=False)
    for uci in line:
        if not isinstance(uci, str):
            raise ValueError("Invalid variation")
        move = chess.Move.from_uci(uci)
        if move not in replay.legal_moves:
            raise ValueError("Illegal variation")
        replay.push(move)
    return line


def _phase(board: chess.Board) -> str:
    # Same material/fullmove rule as upstream analyze.detect_phase.
    pieces = sum(len(board.pieces(pt, color))
                 for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
                 for color in (chess.WHITE, chess.BLACK))
    if pieces <= 6:
        return "endgame"
    return "opening" if board.fullmove_number <= 10 else "middlegame"


def classify_review(fen: str, played_move: str | None, stockfish: dict | None) -> TelemetryClassification:
    """Run the upstream motif classifier on a copy of the existing evidence.

    This is a display-only comparison: it never reads the LLM label or changes
    eligibility, severity, recommendations, lesson counts, or persisted data.
    Missing/contradictory evidence must not masquerade as 'no motif'.
    """
    if played_move is None:
        return TelemetryClassification(status="unavailable", label="Unavailable — no recorded move")
    try:
        board = chess.Board(fen)
        played = chess.Move.from_uci(played_move)
        if not board.is_valid() or played not in board.legal_moves:
            raise ValueError("Invalid review")
        if not isinstance(stockfish, dict) or stockfish.get("perspective") != ("White" if board.turn else "Black"):
            raise ValueError("Mismatched perspective")
        if stockfish.get("fen", fen) != fen:
            raise ValueError("Mismatched position")
        candidates = stockfish.get("top_moves")
        if not isinstance(candidates, list):
            raise ValueError("Missing candidates")
        leaders = [item for item in candidates if isinstance(item, dict) and item.get("rank") == 1]
        actual = stockfish.get("played_move")
        if len(leaders) != 1 or not isinstance(actual, dict) or actual.get("uci") != played_move:
            raise ValueError("Missing matching moves")
        best = leaders[0]
        if (type(best.get("depth")) is not int or best["depth"] < 1
                or type(actual.get("depth")) is not int or actual["depth"] != best["depth"]):
            raise ValueError("Incomparable searches")
        before, after_root = _score(best), _score(actual)
        if _ordered_score(before) < _ordered_score(after_root):
            raise ValueError("Contradictory ranking")
        best_pv, played_pv = _pv(board, best), _pv(board, actual)
        after = board.copy(stack=False)
        after.push(played)
        terminal = after.is_game_over(claim_draw=False)
        if len(played_pv) < 2 and not terminal:
            raise ValueError("Missing opponent reply")
        # The stored PV starts at the original root. Telemetry starts cur at
        # the resulting board, with the opponent to move.
        mate = after_root["mate"]
        if terminal:
            cur = {"cp": None, "mate": 0} if after.is_checkmate() else {"cp": 0, "mate": None}
        else:
            cur = {"cp": -after_root["cp"] if mate is None else None,
                   "mate": (-mate + (1 if mate > 0 else 0)) if mate is not None else None}
        before["pv"] = " ".join(best_pv)
        cur["pv"] = " ".join(played_pv[1:])
        cpl = max(0, min(MATE_CLAMP, _clamped_cp(before) + _clamped_cp(cur)))
    except (ValueError, TypeError):
        return TelemetryClassification(status="unavailable", label="Unavailable — insufficient reliable evidence")

    # Upstream's kept-mate check is strictly negative and overlooks terminal
    # mate=0. A move that delivers checkmate cannot have missed that mate.
    motif = None if after.is_checkmate() else motifs.classify(before, cur, board, played, _phase(board), cpl, MOTIF_MIN_CPL)
    if motif is None:
        return TelemetryClassification(status="below_threshold", label="Below threshold (200 cp)", cp_loss=cpl)
    return TelemetryClassification(status="classified", label=LABELS[motif], motif=motif, cp_loss=cpl)
