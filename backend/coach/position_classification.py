"""Stockfish position evidence and deterministic decision classification."""

import argparse
import asyncio
import json
import sys
from fractions import Fraction
from pathlib import Path

import chess
import chess.engine

from .position import CoachPosition, InvalidPositionError
from .stockfish import (
    StockfishAnalysisError, StockfishSettings, StockfishTimeoutError,
    StockfishUnavailableError, _candidate,
)


def _classification(delta_cp: int | None, delta_e_pp: Fraction) -> str | None:
    # Fractions preserve the inclusive 5/20 pp boundaries of native WDL counts.
    if delta_e_pp >= 20:
        return "Critical"
    if delta_e_pp > 5:
        return "Clear preference"
    if delta_cp is None:
        return None  # A mate score has no centipawn gap to test against 35.
    return "Flexible" if delta_cp <= 35 else "Clear preference"


def _candidate_with_expectation(board: chess.Board, info: dict, rank: int) -> tuple[dict, Fraction]:
    candidate = _candidate(board, info, rank)
    if candidate["score"]["bound"] != "exact":
        raise StockfishAnalysisError("Position classification requires exact scores, not score bounds.")
    reported_wdl = info.get("wdl")
    if not isinstance(reported_wdl, chess.engine.PovWdl):
        raise StockfishAnalysisError("Stockfish did not return win/draw/loss estimates.")
    wdl = reported_wdl.pov(board.turn)
    counts = (wdl.wins, wdl.draws, wdl.losses)
    if any(type(value) is not int or value < 0 for value in counts) or sum(counts) != 1000:
        raise StockfishAnalysisError("Stockfish returned invalid win/draw/loss estimates.")
    expectation = Fraction(2 * wdl.wins + wdl.draws, 2000)
    return {
        **candidate,
        "wdl": {"wins": wdl.wins, "draws": wdl.draws, "losses": wdl.losses},
        "probabilities": {"win": wdl.wins / 1000, "draw": wdl.draws / 1000, "loss": wdl.losses / 1000},
        "expected_score": float(expectation),
    }, expectation


async def _complete_candidates(engine, board: chess.Board, limit: chess.engine.Limit, count: int) -> list[dict]:
    # A timed MultiPV search can stop between candidate lines. Retain the latest
    # complete set instead of comparing moves from different depths.
    iterations: dict[int, dict[int, dict]] = {}
    with await engine.analysis(board, limit, multipv=count) as analysis:
        async for info in analysis:
            depth, rank = info.get("depth"), info.get("multipv")
            if type(depth) is not int or depth < 1 or rank not in range(1, count + 1):
                continue
            if not {"pv", "score", "wdl"} <= info.keys():
                continue
            if info.get("lowerbound") or info.get("upperbound"):
                continue
            iterations.setdefault(depth, {})[rank] = info
    for depth in sorted(iterations, reverse=True):
        if set(iterations[depth]) == set(range(1, count + 1)):
            return [iterations[depth][rank] for rank in range(1, count + 1)]
    raise StockfishAnalysisError("Stockfish did not return all candidate moves at a common depth with WDL estimates.")


async def _analyze_candidates(board: chess.Board, settings: StockfishSettings, count: int) -> tuple[str, list[dict]]:
    transport, engine = await asyncio.wait_for(chess.engine.popen_uci(settings.executable()), timeout=5.0)
    try:
        if "UCI_ShowWDL" not in engine.options:
            raise StockfishUnavailableError("Position classification requires Stockfish with UCI_ShowWDL support.")
        await asyncio.wait_for(engine.configure({"Threads": settings.threads, "Hash": settings.hash_mb, "UCI_ShowWDL": True}), timeout=5.0)
        limit = chess.engine.Limit(depth=settings.depth, time=settings.time_limit)
        # The stream itself has no built-in deadline. Bound the whole search so
        # an unresponsive engine cannot keep a caller waiting indefinitely.
        async with asyncio.timeout(settings.time_limit + 5.0):
            infos = await _complete_candidates(engine, board, limit, count)
        return engine.id.get("name", "Stockfish"), infos
    finally:
        transport.close()


def classify_position(fen: str, settings: StockfishSettings | None = None) -> dict:
    """Classify the best/second-best choice from the side-to-move perspective.

    Blocking, like analyze_move(): async callers should use a worker thread.
    The returned dictionary is JSON-compatible. Unsupported comparisons have a
    null classification and an explicit reason; engine failures raise the shared
    Stockfish exceptions. This function does not persist or trigger coaching.
    """
    return _position_evidence(fen, settings, count=2, analyze_single=False)


def analyze_position(fen: str, settings: StockfishSettings | None = None) -> dict:
    """Top five moves, outlook, relative quality, and the same classification.

    Fewer moves are returned when fewer are legal. A sole legal move is evaluated
    but remains unclassified. Terminal positions need no engine process.
    """
    evidence = _position_evidence(fen, settings, count=5, analyze_single=True)
    labels = {"Flexible": "flexible", "Clear preference": "clear_preference", "Critical": "critical"}
    evidence["decision_classification"] = labels.get(evidence["classification"])
    best = next(iter(evidence["top_moves"]), None)
    evidence["position_outlook"] = {key: best[key] for key in ("score", "wdl", "probabilities", "expected_score")} if best else None
    evidence["permitted_candidate_uci"] = [move["uci"] for move in evidence["top_moves"]]
    return evidence


def _position_evidence(fen: str, settings: StockfishSettings | None, *, count: int, analyze_single: bool) -> dict:
    position = CoachPosition.from_fen(fen)
    board = chess.Board(position.fen)
    legal_move_count = board.legal_moves.count()
    result = {
        "fen": position.fen,
        "perspective": position.side_to_move,
        "legal_move_count": legal_move_count,
        "classification": None,
        "unclassified_reason": None,
        "delta_cp": None,
        "delta_e_pp": None,
        "top_moves": [],
        "engine": None,
        "limits": None,
    }
    if board.is_game_over():
        return {**result, "unclassified_reason": "terminal_position"}
    if legal_move_count < 2 and not analyze_single:
        return {**result, "unclassified_reason": "single_legal_move"}

    settings = settings or StockfishSettings.from_env()
    try:
        engine_name, infos = asyncio.run(_analyze_candidates(board, settings, min(count, legal_move_count)))
        evaluated = [_candidate_with_expectation(board, info, rank) for rank, info in enumerate(infos, 1)]
        candidates = [candidate for candidate, _ in evaluated]
        if len({candidate["uci"] for candidate in candidates}) != len(candidates):
            raise StockfishAnalysisError("Stockfish returned duplicate candidate moves.")
        best, best_e = evaluated[0]
        best_cp = best["score"]["cp"]
        for index, (candidate, expected_score) in enumerate(evaluated):
            if index and (infos[index - 1]["score"].pov(board.turn) < infos[index]["score"].pov(board.turn)
                          or evaluated[index - 1][1] < expected_score):
                raise StockfishAnalysisError("Stockfish candidate scores are inconsistent with their best-move ordering.")
            cp = candidate["score"]["cp"]
            candidate["relative_quality"] = {
                "cp_loss_from_best": best_cp - cp if best_cp is not None and cp is not None else None,
                "expected_score_loss_pp": float(100 * (best_e - expected_score)),
            }
        delta_cp = candidates[1]["relative_quality"]["cp_loss_from_best"] if len(candidates) > 1 else None
        delta_e_pp = 100 * (best_e - evaluated[1][1]) if len(candidates) > 1 else None
        classification = _classification(delta_cp, delta_e_pp) if delta_e_pp is not None else None
        return {
            **result,
            "classification": classification,
            "unclassified_reason": ("single_legal_move" if len(candidates) == 1 else "mate_score") if classification is None else None,
            "delta_cp": delta_cp,
            "delta_e_pp": float(delta_e_pp) if delta_e_pp is not None else None,
            "top_moves": candidates,
            "engine": engine_name,
            "limits": {"depth": settings.depth, "seconds_per_search": settings.time_limit},
            "threads": settings.threads,
            "hash_mb": settings.hash_mb,
        }
    except TimeoutError as exc:
        raise StockfishTimeoutError("Stockfish exceeded its response deadline during position classification.") from exc
    except OSError as exc:
        raise StockfishUnavailableError("Stockfish could not be started. Check its installation and permissions.") from exc
    except chess.engine.EngineError as exc:
        raise StockfishAnalysisError("Stockfish could not complete position classification.") from exc


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    parser = argparse.ArgumentParser(description="Classify a position using Stockfish's top two moves; no model calls.")
    parser.add_argument("--fen", required=True, help="Complete six-field FEN.")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        print(json.dumps(classify_position(args.fen), indent=2, allow_nan=False))
    except (InvalidPositionError, StockfishUnavailableError, StockfishAnalysisError) as exc:
        print(f"Position classification: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
