"""Player-move severity; independent of WDL-based position/candidate policy.

CP curve: https://github.com/lichess-org/scalachess/blob/master/core/src/main/scala/eval.scala
Mate rules: https://github.com/lichess-org/lila/blob/master/modules/tree/src/main/Advice.scala
"""

from copy import deepcopy
import math


ERROR_STATUSES = frozenset({"inaccuracy", "mistake", "blunder"})
ACCEPTABLE_STATUSES = frozenset({"best", "excellent", "good"})
PLAYER_QUALITY_POLICY = {
    "metric": "winning_chances_loss_pp",
    "formula": "100 / (1 + exp(-0.00368208 * clamp(cp, -1000, 1000)))",
    "best_when": "Exact score equals the best move's raw CP or mate score at the same depth.",
    "excellent_max_loss_pp_exclusive": 2.5,
    "good_min_loss_pp": 2.5,
    "inaccuracy_min_loss_pp": 5,
    "mistake_min_loss_pp": 10,
    "blunder_min_loss_pp": 15,
    "mate_policy": "Lichess MateCreated/MateLost rules; exact mate-score ties are best, other retained mates/forced losses are good. Mate distances are not centipawns.",
    "uncertain_when": "Missing scores, bounded scores, different depths, or contradictory ordering.",
}


def win_chance(cp: int) -> float:
    return 100 / (1 + math.exp(-0.00368208 * max(-1000, min(1000, cp))))


def classify_loss(loss: float) -> str:
    """Grade CP loss after checking for a raw-score tie; capped zero is Excellent."""
    if loss >= 15:
        return "blunder"
    if loss >= 10:
        return "mistake"
    if loss >= 5:
        return "inaccuracy"
    return "good" if loss >= 2.5 else "excellent"


def _score(move: dict) -> tuple[str, int] | None:
    score = move.get("score") or {}
    if score.get("bound") != "exact":
        return None
    cp, mate = score.get("cp"), score.get("mate")
    if type(cp) is int and mate is None:
        return "cp", cp
    if type(mate) is int and cp is None:
        return "mate", mate
    return None


def assess_player_move(best: dict, played: dict) -> dict:
    """Scores must already use the player-to-move's perspective at the same root."""
    def result(status, reason, loss=None):
        return {"status": status, "winning_chances_loss_pp": loss, "reason": reason}

    left, right = _score(best), _score(played)
    depth = best.get("depth")
    if (left is None or right is None or type(depth) is not int or depth < 1
            or type(played.get("depth")) is not int or played["depth"] != depth):
        return result("uncertain", "unreliable_evidence")
    best_kind, best_value = left
    played_kind, played_value = right
    if best_kind == played_kind == "cp":
        if best_value < played_value:
            return result("uncertain", "conflicting_order")
        loss = win_chance(best_value) - win_chance(played_value)
        status = "best" if best_value == played_value else classify_loss(loss)
        return result(status, "centipawn_loss", loss)

    # Keep mate transitions separate from the logistic CP calculation. No
    # numerical winning-chance loss is fabricated for forced-mate comparisons.
    if best_kind == "cp" and played_kind == "mate" and played_value <= 0:
        status = "inaccuracy" if best_value < -999 else "mistake" if best_value < -700 else "blunder"
        return result(status, "mate_created")
    if best_kind == "mate" and best_value > 0:
        if played_kind == "cp":
            status = "inaccuracy" if played_value > 999 else "mistake" if played_value > 700 else "blunder"
            return result(status, "mate_lost")
        if played_value > 0:
            return result("best" if best_value == played_value else "good", "mate_retained")
        return result("blunder", "mate_lost")
    if best_kind == played_kind == "mate" and best_value <= 0 and played_value <= 0:
        return result("best" if best_value == played_value else "good", "already_forced_loss")
    return result("uncertain", "conflicting_order")


def with_player_move_quality(evidence: dict) -> dict:
    """Regrade stored scores on read without mutating evidence or running engines."""
    result = deepcopy(evidence)
    best = next(iter(result.get("top_moves") or []), {})
    played = result.get("played_move") or {}
    quality = assess_player_move(best, played)
    result["move_quality"] = quality
    result["move_quality_policy"] = PLAYER_QUALITY_POLICY.copy()
    if played:
        result["played_move"] = {**played, "quality": quality}
    return result
