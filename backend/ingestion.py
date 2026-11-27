"""Phase 1: source facts and board features. No engine or model calls."""

import hashlib
import re
from datetime import datetime, timezone

import chess

from .chess_games import parse_game
from .game_phase import next_phase

INGESTION_VERSION = 1
PIECES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def utc(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc) if seconds is not None else None


def termination(raw, game):
    codes = [raw.get(color, {}).get("result") for color in ("white", "black")]
    mapping = {"checkmated": "checkmate", "resigned": "resignation", "timeout": "timeout",
               "timevsinsufficient": "timeout_insufficient_material", "stalemate": "stalemate",
               "agreed": "agreement", "repetition": "repetition", "50move": "fifty_move_rule",
               "insufficient": "insufficient_material", "abandoned": "abandonment"}
    for code in codes:
        if code in mapping:
            return mapping[code], code
    outcome = game.end().board().outcome()
    return (outcome.termination.name.lower() if outcome else "unknown", game.headers.get("Termination"))


def import_records(record, now):
    game = parse_game(record["pgn"])
    board = game.board()
    raw = record.get("raw_metadata") or {}
    control_raw = raw.get("time_control", record.get("time_control", game.headers.get("TimeControl", "")))
    control = re.fullmatch(r"(\d+)(?:\+(\d+))?", control_raw)
    base = float(control[1]) if control else None
    increment = float(control[2] or 0) if control else None
    start = utc(raw.get("start_time"))
    if start is None:
        try:
            start = datetime.strptime(f"{game.headers['UTCDate']} {game.headers['UTCTime']}", "%Y.%m.%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            pass
    ending, ending_raw = termination(raw, game)
    fields = {
        "game_id": record["id"], "source": "chess.com", "source_game_id": str(raw["uuid"]) if raw.get("uuid") else None,
        "source_url": record["url"], "white_username": record["white"], "white_rating": record.get("white_rating"),
        "black_username": record["black"], "black_rating": record.get("black_rating"),
        "started_at": start, "ended_at": utc(record["end_time"]), "imported_at": utc(now),
        "rated": raw.get("rated"), "variant": "standard", "result": record["result"],
        "termination": ending, "termination_raw": ending_raw, "time_class": record.get("time_class", "unknown"),
        "time_control_raw": control_raw, "initial_seconds": base, "increment_seconds": increment,
        "time_control_status": "parsed" if control else "unsupported" if control_raw else "missing",
        "opening_name": record.get("opening") or None, "opening_family": None, "eco_code": record.get("eco") or None,
        "initial_fen": board.fen(), "raw_pgn": record["pgn"], "raw_metadata": raw,
        "pgn_hash": hashlib.sha256(record["pgn"].encode()).hexdigest(), "ingestion_version": INGESTION_VERSION,
    }
    clocks = {chess.WHITE: base if board.ply() == 0 else None, chess.BLACK: base if board.ply() == 0 else None}
    phase = next_phase(board)
    moves = []
    for ply, node in enumerate(game.mainline()):
        move, color = node.move, board.turn
        clock_before, clock_after, elapsed = clocks[color], node.clock(), node.emt()
        source = "pgn_elapsed" if elapsed is not None else "unavailable"
        if elapsed is None and clock_before is not None and clock_after is not None and increment is not None:
            elapsed = clock_before + increment - clock_after
            source = "clock_calculation"
        status = "valid" if elapsed is not None else "unsupported" if not control else "missing"
        if any(value is not None and value < 0 for value in (clock_before, clock_after, elapsed)):
            status, elapsed = "inconsistent", None
        counts = {name: {chess.piece_name(piece): len(board.pieces(piece, side)) for piece in PIECES}
                  for name, side in (("white", chess.WHITE), ("black", chess.BLACK))}
        material = sum(value * (len(board.pieces(piece, color)) - len(board.pieces(piece, not color)))
                       for piece, value in PIECES.items())
        captured = chess.PAWN if board.is_en_passant(move) else board.piece_type_at(move.to_square)
        row = {"game_id": record["id"], "decision_ply": ply, "move_number": board.fullmove_number,
               "color": "white" if color else "black", "uci": move.uci(), "san": board.san(move), "fen_before": board.fen(),
               "clock_before_seconds": clock_before, "clock_after_seconds": clock_after, "time_spent_seconds": elapsed,
               "timing_source": source, "timing_status": status, "piece_moved": chess.piece_name(board.piece_type_at(move.from_square)),
               "is_capture": board.is_capture(move), "captured_piece": chess.piece_name(captured) if captured else None,
               "gives_check": board.gives_check(move), "is_castling": board.is_castling(move),
               "promotion_piece": chess.piece_name(move.promotion) if move.promotion else None,
               "legal_moves_before": board.legal_moves.count(), "piece_counts_before": counts,
               "material_balance_before": material, "phase_before": phase}
        board.push(move)
        row["fen_after"] = board.fen()
        moves.append(row)
        phase = next_phase(board, phase)
        clocks[color] = clock_after
    return fields, moves


def game_api(row, ply_count):
    """Keep the public game contract independent from database column names."""
    return {"id": row["game_id"], "url": row["source_url"], "pgn": row["raw_pgn"],
            "white": row["white_username"], "black": row["black_username"],
            "white_rating": row["white_rating"], "black_rating": row["black_rating"],
            "result": row["result"], "end_time": int(row["ended_at"].timestamp()),
            "time_class": row["time_class"], "time_control": row["time_control_raw"],
            "opening": row["opening_name"] or "", "eco": row["eco_code"] or "", "ply_count": ply_count,
            "analysis_revision": row["analysis_revision"]}
