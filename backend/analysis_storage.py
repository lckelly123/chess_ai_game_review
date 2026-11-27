"""Phase 2 storage adapters. Persist White-relative evidence, reconstruct API views."""

from copy import deepcopy

import chess

from .coach.player_move_quality import PLAYER_QUALITY_POLICY, with_player_move_quality
from .coach.sharpness import SHARPNESS_VERSION, with_position_sharpness

EVIDENCE_VERSION = 1


def orient_evidence(value, black):
    """An involution: flip signed scores, bounds and WDL together, never ranks."""
    if isinstance(value, list):
        return [orient_evidence(item, black) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: orient_evidence(item, black) for key, item in value.items()}
    if not black:
        return result
    if "cp" in result and "mate" in result:
        for key in ("cp", "mate"):
            if result[key] is not None:
                result[key] = -result[key]
        if result.get("bound") in ("lower", "upper"):
            result["bound"] = "upper" if result["bound"] == "lower" else "lower"
    if all(key in result for key in ("wins", "draws", "losses")):
        result["wins"], result["losses"] = result["losses"], result["wins"]
    if all(key in result for key in ("win", "draw", "loss")):
        result["win"], result["loss"] = result["loss"], result["win"]
    if result.get("expected_score") is not None:
        result["expected_score"] = 1 - result["expected_score"]
    if "perspective" in result:
        result["perspective"] = "White" if result["perspective"] == "Black" else "Black"
    return result


def engine_columns(row, result, fingerprint):
    stockfish = result["stockfish"]
    if (stockfish.get("fen", result.get("fen")) != row["fen_before"] or result.get("fen") != row["fen_before"]
            or result.get("played_move") != row["uci"] or stockfish.get("perspective") != row["color"].title()):
        raise ValueError("Engine evidence does not match the recorded move.")
    black = row["color"] == "black"
    position = result.get("position_evidence") or stockfish
    candidates = stockfish["top_moves"][:5]
    played = next((item for item in candidates if item["uci"] == row["uci"]), stockfish["played_move"])
    white = orient_evidence({"candidates": candidates, "played": played}, black)
    columns = {}
    for name, item in [(f"top_{i}", white["candidates"][i-1] if i <= len(candidates) else None) for i in range(1, 6)] + [("played", white["played"])]:
        if name != "played":
            columns[f"{name}_uci"] = item["uci"] if item else None
        for key in ("cp", "mate", "bound"):
            columns[f"{name}_{key}"] = item.get("score", {}).get(key) if item else None
        columns[f"{name}_depth"] = item.get("depth") if item else None
        columns[f"{name}_pv_uci"] = item.get("pv_uci", []) if item else None
    aux = {item["uci"]: {key: item[key] for key in ("wdl", "probabilities", "expected_score") if key in item}
           for item in white["candidates"] + [white["played"]]}
    source = stockfish.get("played_evaluation_source") or ("candidate_reuse" if any(c["uci"] == row["uci"] for c in candidates) else "separate_search")
    metadata = {"perspective": "White", "analysis_fingerprint": fingerprint,
                "position_search": {"limits": position.get("limits"), "threads": position.get("threads"),
                                    "hash_mb": position.get("hash_mb"), "multipv": len(candidates),
                                    "root_scope": "all_legal_moves", "history_mode": "fen_only", "engine": position.get("engine")},
                "searches": stockfish.get("search_metadata"), "candidate_aux": aux,
                "policies": {"sharpness": SHARPNESS_VERSION, "move_quality": PLAYER_QUALITY_POLICY}}
    if source == "comparison" and (stockfish.get("search_metadata") or {}).get("comparison"):
        metadata["position_search"].update(stockfish["search_metadata"]["comparison"])
    columns.update(engine_status="completed", engine_name=stockfish.get("engine"),
                   engine_pgn_hash=row["pgn_hash"], engine_evidence_version=EVIDENCE_VERSION,
                   engine_search_metadata=metadata, engine_error=None, played_evaluation_source=source,
                   engine_comparison_evidence=orient_evidence(stockfish.get("comparison_evidence"), black))
    return columns


def _candidate(row, prefix, uci, rank):
    board = chess.Board(row["fen_before"])
    san = board.san(chess.Move.from_uci(uci))
    pv = row.get(f"{prefix}_pv_uci") or []
    pv_san = []
    for move in pv:
        parsed = chess.Move.from_uci(move)
        if parsed not in board.legal_moves:
            break
        pv_san.append(board.san(parsed))
        board.push(parsed)
    aux = (row.get("engine_search_metadata") or {}).get("candidate_aux", {}).get(uci, {})
    return orient_evidence({**deepcopy(aux), "uci": uci, "san": san, "rank": rank,
                            "score": {key: row.get(f"{prefix}_{key}") for key in ("cp", "mate", "bound")},
                            "depth": row.get(f"{prefix}_depth"), "pv_uci": pv, "pv_san": pv_san}, row["color"] == "black")


def engine_result(row):
    candidates = [_candidate(row, f"top_{n}", row[f"top_{n}_uci"], n) for n in range(1, 6) if row.get(f"top_{n}_uci")]
    played = next((c for c in candidates if c["uci"] == row["uci"]), None)
    played = deepcopy(played) if played else _candidate(row, "played", row["uci"], None)
    metadata = row.get("engine_search_metadata") or {}
    search = metadata.get("position_search") or {}
    position = with_position_sharpness({"fen": row["fen_before"], "perspective": row["color"].title(),
                                       "engine": row["engine_name"], "top_moves": candidates,
                                       "limits": search.get("limits"), "threads": search.get("threads"),
                                       "hash_mb": search.get("hash_mb")})
    stockfish = with_player_move_quality({**position, "played_move": played,
                                         "played_move_in_top": any(c["uci"] == row["uci"] for c in candidates),
                                         "played_evaluation_source": row.get("played_evaluation_source"),
                                         "move_quality_policy": PLAYER_QUALITY_POLICY})
    return {"fen": row["fen_before"], "played_move": row["uci"], "position_evidence": position, "stockfish": stockfish}


def derived_columns(row):
    """Phase 2.5 reads only persisted phase 2.0 evidence."""
    result = engine_result(row)
    position = result["position_evidence"]
    tag = position["decision_classification"]
    return {"sharpness_score": position["sharpness"]["score"],
            "sharpness_classification": tag.title() if tag else None,
            "move_quality": result["stockfish"]["move_quality"]["status"].title()}
