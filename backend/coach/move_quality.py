"""Outcome-based move quality for the combined coaching card."""

from copy import deepcopy
from dataclasses import replace
from fractions import Fraction

import chess
import chess.engine

from .move_review import MoveReview
from .player_move_quality import ACCEPTABLE_STATUSES, PLAYER_QUALITY_POLICY, assess_player_move
from .position_classification import compare_candidate_moves
from .sharpness import with_position_sharpness
from .stockfish import StockfishAnalysisError, StockfishSettings, StockfishTimeoutError, StockfishUnavailableError, _candidate

# Legacy WDL comparison remains available for existing evidence consumers.
# New teaching candidates use the shared player-severity classifier below.
ACCEPTABLE_LOSS_PP = 5
QUALITY_POLICY = {
    "metric": "expected_score_loss_pp",
    "acceptable_max_loss_pp": ACCEPTABLE_LOSS_PP,
    "meaningfully_inferior_above_pp": ACCEPTABLE_LOSS_PP,
    "uncertain_when": "Missing WDL, bounded scores, different depths, or contradictory ordering.",
}


def expectation(move: dict) -> Fraction | None:
    wdl = move.get("wdl") or {}
    counts = [wdl.get(key) for key in ("wins", "draws", "losses")]
    if any(type(value) is not int or value < 0 for value in counts) or sum(counts) != 1000:
        return None
    return Fraction(2 * counts[0] + counts[1], 2000)


def improvement_pp(better: dict, other: dict) -> Fraction | None:
    left, right = expectation(better), expectation(other)
    if (left is None or right is None or better.get("depth", 0) < 1
            or better.get("depth") != other.get("depth")
            or any(move.get("score", {}).get("bound") != "exact" for move in (better, other))):
        return None
    return 100 * (left - right)


def assess_move(best: dict, move: dict) -> dict:
    """Legacy WDL comparison; not used to select new teaching candidates."""
    loss = improvement_pp(best, move)
    # A separately searched root may contradict the initial MultiPV ranking.
    # Do not convert conflicting evidence into praise or a severity label.
    def ordered_score(item):
        score = item.get("score", {})
        mate, cp = score.get("mate"), score.get("cp")
        if mate is not None:
            return (2, -mate) if mate > 0 else (0, -mate)
        return (1, cp) if cp is not None else None
    best_score, move_score = ordered_score(best), ordered_score(move)
    if loss is None or loss < 0 or best_score is None or move_score is None or best_score < move_score:
        return {"status": "uncertain", "expected_score_loss_pp": None}
    return {"status": "acceptable" if loss <= ACCEPTABLE_LOSS_PP else "meaningfully_inferior",
            "expected_score_loss_pp": float(loss)}


def prepare_position_evidence(evidence: dict) -> dict:
    """Approve moves without consulting any player-specific information."""
    result = with_position_sharpness(deepcopy(evidence))
    candidates = result["top_moves"]
    for move in candidates:
        move["quality"] = assess_player_move(candidates[0], move)
    # Keep all raw lines and WDL metadata for consumers, but select the exact
    # teaching list with the same severity rules used to grade practice moves.
    result["permitted_candidate_uci"] = [move["uci"] for move in candidates
                                         if move["quality"]["status"] in ACCEPTABLE_STATUSES][:3]
    result["move_quality_policy"] = PLAYER_QUALITY_POLICY.copy()
    return result


def _played_candidate(board: chess.Board, info: dict) -> dict:
    # Legal move/score/PV evidence is still useful when WDL or an exact score is
    # unavailable. Preserve it for Case D rather than awarding a quality label.
    played = _candidate(board, info, None)
    reported = info.get("wdl")
    if isinstance(reported, chess.engine.PovWdl):
        wdl = reported.pov(board.turn)
        counts = {"wins": wdl.wins, "draws": wdl.draws, "losses": wdl.losses}
        expected = expectation({"wdl": counts})
        if expected is not None:
            played.update(wdl=counts, expected_score=float(expected),
                          probabilities={"win": wdl.wins / 1000, "draw": wdl.draws / 1000, "loss": wdl.losses / 1000})
    return played


def _comparison_position(evidence: dict, candidates: list[dict], engine: str, settings: StockfishSettings) -> dict:
    """Replace the position's ranked evidence with the verified top five."""
    best = candidates[0]
    best_cp, best_e = best["score"]["cp"], expectation(best)
    for move in candidates:
        cp = move["score"]["cp"]
        move["relative_quality"] = {
            "cp_loss_from_best": best_cp - cp if best_cp is not None and cp is not None else None,
            "expected_score_loss_pp": float(100 * (best_e - expectation(move))),
        }
    second = candidates[1]["relative_quality"] if len(candidates) > 1 else {}
    return prepare_position_evidence({
        **evidence, "engine": engine, "top_moves": candidates,
        "delta_cp": second.get("cp_loss_from_best"), "delta_e_pp": second.get("expected_score_loss_pp"),
        "position_outlook": {key: best[key] for key in ("score", "wdl", "probabilities", "expected_score")},
        "limits": {"depth": settings.depth, "seconds_per_search": settings.time_limit},
        "threads": settings.threads, "hash_mb": settings.hash_mb,
    })


def analyze_played_move(review: MoveReview, evidence: dict, settings: StockfishSettings | None = None) -> dict:
    """Grade the move without running the disabled Lichess motif detectors."""
    review = MoveReview.from_fen(review.position.fen, review.played_move_uci)
    if evidence.get("fen") != review.position.fen or evidence.get("perspective") != review.position.side_to_move:
        raise StockfishAnalysisError("Stockfish evidence did not match the selected position.")
    candidates = evidence["top_moves"]
    if not candidates:
        raise StockfishAnalysisError("No position evidence is available for this move.")
    played = next((move for move in candidates if move["uci"] == review.played_move_uci), None)
    in_top = played is not None
    engine_name = evidence["engine"]
    searches = {"position": {"limits": evidence.get("limits"), "threads": evidence.get("threads"),
        "hash_mb": evidence.get("hash_mb"), "multipv": len(candidates), "root_scope": "all_legal_moves", "history_mode": "fen_only"}}
    source = "candidate_reuse" if in_top else "separate_search"
    if played is None:
        settings = settings or StockfishSettings.from_env()
        # Compare at the completed position search's depth, not the requested
        # depth which a timed MultiPV search may never have reached.
        settings = replace(settings, depth=candidates[0]["depth"])
        searches["played"] = {"limits": {"depth": settings.depth, "seconds_per_search": settings.time_limit},
            "threads": settings.threads, "hash_mb": settings.hash_mb, "multipv": 1,
            "root_scope": [review.played_move_uci], "history_mode": "fen_only"}
        board = chess.Board(review.position.fen)
        try:
            with chess.engine.SimpleEngine.popen_uci(settings.executable(), timeout=5.0) as engine:
                if "UCI_ShowWDL" not in engine.options:
                    raise StockfishUnavailableError("Move quality requires Stockfish with UCI_ShowWDL support.")
                engine.configure({"Threads": settings.threads, "Hash": settings.hash_mb, "UCI_ShowWDL": True})
                info = engine.analyse(board, chess.engine.Limit(depth=settings.depth, time=settings.time_limit),
                                      root_moves=[chess.Move.from_uci(review.played_move_uci)])
                played = _played_candidate(board, info)
                engine_name = engine.id.get("name", "Stockfish")
        except TimeoutError as exc:
            raise StockfishTimeoutError("Stockfish exceeded its response deadline for the played move.") from exc
        except OSError as exc:
            raise StockfishUnavailableError("Stockfish could not be started.") from exc
        except chess.engine.EngineError as exc:
            raise StockfishAnalysisError("Stockfish could not evaluate the played move.") from exc
    if played["uci"] != review.played_move_uci:
        raise StockfishAnalysisError("Stockfish evaluated a different played move.")
    quality = assess_player_move(candidates[0], played)
    verified_position = None
    comparison = None
    if not in_top and quality["reason"] == "conflicting_order":
        # Separate searches can disagree even at the same depth. Compare all
        # original candidates and the player together; never sort mixed scores
        # or turn a negative loss into an automatic Good grade.
        comparison = {"original_candidates": deepcopy(candidates), "original_played": deepcopy(played)}
        source = "comparison"
        searches["comparison"] = {**searches["played"], "multipv": len(candidates) + 1,
                                  "root_scope": [move["uci"] for move in candidates] + [played["uci"]]}
        engine_name, compared = compare_candidate_moves(
            review.position.fen, [move["uci"] for move in candidates] + [played["uci"]], settings)
        played = next(move for move in compared if move["uci"] == review.played_move_uci)
        comparison["compared_candidates"] = deepcopy(compared)
        candidates = compared[:len(candidates)]
        verified_position = _comparison_position(evidence, candidates, engine_name, settings)
        candidates = verified_position["top_moves"]
        in_top = any(move["uci"] == played["uci"] for move in candidates)
        quality = assess_player_move(candidates[0], played)
    played = {**played, "quality": quality}
    return {"fen": review.position.fen, "engine": engine_name, "perspective": review.position.side_to_move,
            "top_moves": candidates, "played_move": played, "played_move_in_top": in_top,
            "move_quality": played["quality"], "move_quality_policy": PLAYER_QUALITY_POLICY.copy(),
            "played_evaluation_source": source, "search_metadata": searches, "comparison_evidence": comparison,
            **({"position_evidence": verified_position} if verified_position is not None else {})}
