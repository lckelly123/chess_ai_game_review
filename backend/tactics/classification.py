"""Classify error continuations using a bounded subset of Lichess puzzle rules.

The root search establishes error eligibility. These tags describe motifs in
the two lines, not a proof that a motif uniquely caused the evaluation loss.
Engine work is confined to analysis; response serialization only reads results.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

import chess
import chess.engine
import chess.pgn

from ..coach.player_move_quality import ERROR_STATUSES, assess_player_move
from ..coach.stockfish import StockfishSettings, StockfishUnavailableError
from .lichess import cook

VERSION = 1
SOURCE_REVISION = "8e24b6d5e2b9618e41581a327926e4ac67c610a2"
MAX_PLIES = 16  # Eight moves by each side, starting with the tactic's actor.
EXTENSION_NODES = 200_000
EXTENSION_SECONDS = 2.0


@dataclass
class MotifLine:
    game: chess.pgn.Game
    mainline: list
    pov: chess.Color


def _pin(line: MotifLine) -> bool:
    return cook.pin_prevents_attack(line) or cook.pin_prevents_escape(line)


DETECTORS: tuple[tuple[str, Callable], ...] = (
    ("fork", cook.fork),
    ("hanging_piece", cook.hanging_piece),
    ("skewer", cook.skewer),
    ("discovered_attack", cook.discovered_attack),
    ("pin", _pin),
    ("double_check", cook.double_check),
)


def _variation(board: chess.Board, candidate: dict) -> list[chess.Move]:
    values = candidate.get("pv_uci")
    if not isinstance(values, list) or not values or values[0] != candidate.get("uci"):
        raise ValueError("Missing root continuation")
    replay = board.copy(stack=False)
    moves = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError("Invalid continuation")
        move = chess.Move.from_uci(value)
        if move not in replay.legal_moves:
            raise ValueError("Illegal continuation")
        moves.append(move)
        replay.push(move)
    return moves


def _line(board: chess.Board, moves: list[chess.Move], setup: chess.Move | None = None) -> MotifLine:
    game = chess.pgn.Game.from_board(board)
    node = game
    if setup is not None:
        node = node.add_main_variation(setup)
    # Lichess indexes the position AFTER the setup move as mainline[0].
    # At a standalone best-move root there is no preceding move to fabricate.
    mainline = [node]
    pov = node.board().turn
    for move in moves:
        node = node.add_main_variation(move)
        mainline.append(node)
    return MotifLine(game, mainline, pov)


def detect_motifs(board: chess.Board, moves: list[chess.Move], *, setup: chess.Move | None = None) -> list[str]:
    if not moves:
        return []
    line = _line(board, moves, setup)
    return [name for name, detector in DETECTORS if detector(line)]


def _extend(board: chess.Board, moves: list[chess.Move], settings: StockfishSettings) -> list[chess.Move]:
    """One bounded search at a line's leaf; never replace the root score or PV."""
    leaf = board.copy(stack=False)
    for move in moves:
        leaf.push(move)
    with chess.engine.SimpleEngine.popen_uci(settings.executable(), timeout=5.0) as engine:
        engine.configure({"Threads": settings.threads, "Hash": settings.hash_mb})
        info = engine.analyse(leaf, chess.engine.Limit(
            depth=settings.depth, time=min(settings.time_limit, EXTENSION_SECONDS), nodes=EXTENSION_NODES))
    if not info.get("pv") or info.get("lowerbound") or info.get("upperbound"):
        raise ValueError("Incomplete extension")
    extended = list(moves)
    for move in info["pv"][:MAX_PLIES - len(moves)]:
        if move not in leaf.legal_moves:
            raise ValueError("Illegal extension")
        extended.append(move)
        leaf.push(move)
        if leaf.is_game_over():
            break
    return extended


def _inspect(board: chess.Board, candidate: dict, direction: str, *, settings: StockfishSettings | None,
             allow_engine: bool, extend: Callable) -> dict:
    branch = {"direction": direction, "motifs": [], "line_uci": [], "extended": False,
              "coverage": "insufficient", "reason": None}
    try:
        root_moves = _variation(board, candidate)
    except (ValueError, TypeError):
        return {**branch, "reason": "invalid_or_missing_line"}
    setup = root_moves[0] if direction == "allowed" else None
    start = board.copy(stack=False)
    if setup is not None:
        start.push(setup)
    moves = (root_moves[1:] if setup is not None else root_moves)[:MAX_PLIES]
    leaf = start.copy(stack=False)
    for move in moves:
        leaf.push(move)
    if len(moves) < MAX_PLIES and not leaf.is_game_over() and allow_engine:
        try:
            moves = extend(start, moves, settings or StockfishSettings.from_env())
            # Validate extensions supplied by the engine or an injected test provider.
            leaf = start.copy(stack=False)
            for move in moves:
                if move not in leaf.legal_moves:
                    raise ValueError("Illegal extended line")
                leaf.push(move)
            branch["extended"] = True
        except (ValueError, OSError, TimeoutError, chess.engine.EngineError, StockfishUnavailableError):
            # Preserve the valid cached prefix, but never present this as a full inspection.
            moves = (root_moves[1:] if setup is not None else root_moves)[:MAX_PLIES]
            leaf = start.copy(stack=False)
            for move in moves:
                leaf.push(move)
            branch["reason"] = "extension_unavailable"
    branch["line_uci"] = [move.uci() for move in moves]
    branch["side"] = "white" if start.turn else "black"
    branch["coverage"] = "terminal" if leaf.is_game_over() else "bounded" if len(moves) >= MAX_PLIES else "insufficient"
    if branch["coverage"] == "insufficient" and branch["reason"] is None:
        branch["reason"] = "short_line"
    branch["motifs"] = detect_motifs(board, moves, setup=setup)
    return branch


def classify_review(fen: str, played_move: str | None, evidence: dict | None, *,
                    settings: StockfishSettings | None = None, allow_engine: bool = False,
                    extend: Callable = _extend) -> dict:
    """Pure on cached data by default; ingestion explicitly permits leaf searches."""
    result = {"version": VERSION, "source": "lichess-puzzler", "source_revision": SOURCE_REVISION,
              "fen": fen, "played_move": played_move, "status": "insufficient_evidence",
              "reason": None, "max_plies": MAX_PLIES, "lines": []}
    if played_move is None:
        return {**result, "status": "not_applicable", "reason": "no_recorded_move"}
    try:
        board = chess.Board(fen)
        played = chess.Move.from_uci(played_move)
        if not board.is_valid() or played not in board.legal_moves:
            raise ValueError("Invalid position or move")
        if not isinstance(evidence, dict) or evidence.get("fen", fen) != fen:
            raise ValueError("Missing matching evidence")
        if evidence.get("perspective") != ("White" if board.turn else "Black"):
            raise ValueError("Mismatched perspective")
        leaders = [move for move in evidence.get("top_moves", []) if move.get("rank") == 1]
        actual = evidence.get("played_move", {})
        if len(leaders) != 1 or actual.get("uci") != played_move:
            raise ValueError("Missing matching moves")
        best = leaders[0]
        quality = assess_player_move(best, actual)
    except (ValueError, TypeError, AttributeError):
        return {**result, "reason": "unreliable_evidence"}
    if quality["status"] == "uncertain":
        return {**result, "reason": "unreliable_evidence"}
    if quality["status"] not in ERROR_STATUSES:
        return {**result, "status": "not_applicable", "reason": "not_an_error"}
    if best.get("uci") == played_move:
        return {**result, "reason": "conflicting_root_moves"}
    result["lines"] = [
        _inspect(board, candidate, direction, settings=settings, allow_engine=allow_engine, extend=extend)
        for candidate, direction in ((best, "missed"), (actual, "allowed"))
    ]
    if any(line["motifs"] for line in result["lines"]):
        result["status"] = "classified"
    elif all(line["coverage"] != "insufficient" for line in result["lines"]):
        result["status"] = "unclassified"
    else:
        result["reason"] = "incomplete_lines"
    return result


def with_tactic_classification(fen: str, played_move: str, evidence: dict, *,
                              settings: StockfishSettings | None = None, allow_engine: bool = True) -> dict:
    result = deepcopy(evidence)
    result["tactic_classification"] = classify_review(fen, played_move, evidence,
                                                     settings=settings, allow_engine=allow_engine)
    return result
