"""White-oriented position timeline and Lichess game accuracy.

Algorithm source: lichess-org/lila modules/analyse/src/main/AccuracyPercent.scala
and modules/tree/src/main/eval.scala (verified 2026-11-26).
"""

import math
from statistics import pstdev

import chess

STATISTICS_VERSION = 1


def win_percent(cp: float) -> float:
    return 100 / (1 + math.exp(-0.00368208 * max(-1000, min(1000, cp))))


def move_accuracy(before: float, after: float) -> float:
    if after >= before:
        return 100.0
    return max(0.0, min(100.0, 103.1668100711649 * math.exp(-0.04354415386753951 * (before - after))
                        - 3.166924740191411 + 1))


def game_accuracy(cps: list[float], start_color: str) -> dict:
    """Exact Lichess volatility-weighted / harmonic aggregation, without rounding."""
    if len(cps) < 3:
        return {"white": None, "black": None}
    wins = [win_percent(cp) for cp in cps]
    size = max(2, min(8, (len(cps) - 1) // 10))
    windows = [wins[:size]] * max(0, min(size, len(wins)) - 2)
    windows += [wins[i:i + size] for i in range(max(1, len(wins) - size + 1))]
    by_color = {"white": [], "black": []}
    for index, (before, after, window) in enumerate(zip(wins, wins[1:], windows)):
        color = start_color if index % 2 == 0 else ("black" if start_color == "white" else "white")
        accuracy = move_accuracy(before, after) if color == "white" else move_accuracy(after, before)
        by_color[color].append((accuracy, max(0.5, min(12, pstdev(window)))))
    result = {}
    for color, values in by_color.items():
        if not values:
            result[color] = None
            continue
        weighted = sum(accuracy * weight for accuracy, weight in values) / sum(weight for _, weight in values)
        harmonic = len(values) / sum(1 / max(1, accuracy) for accuracy, _ in values)
        result[color] = (weighted + harmonic) / 2
    return result


def position_evaluation(evidence: dict, ply: int, fen: str) -> dict | None:
    """Use the best ranked line, never substitute a separately searched played score."""
    if evidence.get("fen", fen) != fen:
        return None
    expected_perspective = "White" if chess.Board(fen).turn else "Black"
    if evidence.get("perspective") != expected_perspective:
        return None
    best = next(iter(evidence.get("top_moves") or []), {})
    score = best.get("score", {})
    cp, mate = score.get("cp"), score.get("mate")
    if score.get("bound") != "exact" or not isinstance(best.get("depth"), int) or best["depth"] < 1:
        return None
    if (cp is None) == (mate is None) or type(cp if cp is not None else mate) is not int:
        return None
    sign = 1 if expected_perspective == "White" else -1
    winner = None if mate is None else (expected_perspective.lower() if mate > 0 else
                                       ("black" if expected_perspective == "White" else "white"))
    return {"ply": ply, "fen": fen, "status": "evaluated", "cp": cp * sign if cp is not None else None,
            "mate": mate * sign if mate is not None else None, "mate_winner": winner,
            "depth": best["depth"], "engine": evidence.get("engine"), "source": "position_search",
            "limits": evidence.get("limits"), "threads": evidence.get("threads"), "hash_mb": evidence.get("hash_mb")}


def terminal_evaluation(board: chess.Board, ply: int, *, claim_draw: bool = False) -> dict | None:
    # A resignation/time-out result is not a terminal board evaluation.
    outcome = board.outcome(claim_draw=claim_draw)
    if outcome is None:
        return None
    winner = None if outcome.winner is None else ("white" if outcome.winner else "black")
    return {"ply": ply, "fen": board.fen(), "status": "terminal", "cp": 0 if winner is None else None,
            "mate": None if winner is None else 0, "mate_winner": winner, "depth": None,
            "engine": None, "source": "game_rules", "termination": outcome.termination.name.lower()}


def evaluation_cp(point: dict) -> float:
    if point["cp"] is not None:
        return point["cp"]
    return 1000 if point["mate_winner"] == "white" else -1000


def build_statistics(detail: dict, reviews: dict, final: dict) -> dict:
    timeline = []
    for ply, position in enumerate(detail["positions"][:-1]):
        review = reviews.get(str(ply), {})
        point = None
        if review.get("fen") == position["fen"] and review.get("played_move") == detail["moves"][ply]["uci"]:
            point = position_evaluation({**(review.get("position_evidence") or {}), **review.get("stockfish", {})}, ply, position["fen"])
        timeline.append(point or {"ply": ply, "fen": position["fen"], "status": "missing"})
    timeline.append(final)
    complete = all(point["status"] != "missing" for point in timeline)
    start = "white" if chess.Board(detail["positions"][0]["fen"]).turn else "black"
    return {"version": STATISTICS_VERSION, "perspective": "White", "complete": complete, "timeline": timeline,
            "accuracy": game_accuracy([evaluation_cp(point) for point in timeline], start) if complete else
            {"white": None, "black": None}}
