"""Local engine evidence, independent of OpenAI calls."""

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import sys
from dataclasses import dataclass

import chess
import chess.engine

from .move_review import MoveReview
from .position import InvalidPositionError


class StockfishUnavailableError(RuntimeError):
    pass


class StockfishAnalysisError(RuntimeError):
    pass


class StockfishTimeoutError(StockfishAnalysisError):
    pass


@dataclass(frozen=True)
class StockfishSettings:
    path: str | None = None
    depth: int = 18
    time_limit: float = 10.0
    threads: int = 2
    hash_mb: int = 128

    def __post_init__(self):
        if not 1 <= self.depth <= 40:
            raise StockfishUnavailableError("STOCKFISH_DEPTH must be between 1 and 40.")
        if not math.isfinite(self.time_limit) or not 0 < self.time_limit <= 120:
            raise StockfishUnavailableError("STOCKFISH_TIME_LIMIT must be greater than 0 and at most 120 seconds.")
        if not 1 <= self.threads <= 32 or not 16 <= self.hash_mb <= 4096:
            raise StockfishUnavailableError("Stockfish threads must be 1–32 and hash memory 16–4096 MB.")

    @classmethod
    def from_env(cls) -> "StockfishSettings":
        try:
            return cls(
                path=os.getenv("STOCKFISH_PATH") or None,
                depth=int(os.getenv("STOCKFISH_DEPTH", "18")),
                time_limit=float(os.getenv("STOCKFISH_TIME_LIMIT", "10")),
                threads=int(os.getenv("STOCKFISH_THREADS", "2")),
                hash_mb=int(os.getenv("STOCKFISH_HASH_MB", "128")),
            )
        except ValueError as exc:
            raise StockfishUnavailableError("Invalid numeric Stockfish setting.") from exc

    def executable(self) -> str:
        if self.path:
            executable = shutil.which(self.path)
            if executable:
                return executable
            raise StockfishUnavailableError("STOCKFISH_PATH does not point to an executable.")
        executable = shutil.which("stockfish")
        if executable:
            return executable
        local = Path(__file__).resolve().parents[2] / ".tools" / "stockfish"
        marker = local / "executable.txt"
        if marker.is_file():
            executable_path = local / marker.read_text(encoding="utf-8").strip()
            if executable_path.is_file():
                return str(executable_path)
        raise StockfishUnavailableError("Install Stockfish with scripts/install_stockfish.py or set STOCKFISH_PATH.")


def _candidate(board: chess.Board, info: dict, rank: int | None) -> dict:
    pv = info.get("pv")
    score = info.get("score")
    if not pv or score is None or info.get("depth", 0) < 1:
        raise StockfishAnalysisError("Stockfish returned incomplete move evidence.")
    line_board = board.copy(stack=False)
    san_line = []
    for move in pv:
        if move not in line_board.legal_moves:
            raise StockfishAnalysisError("Stockfish returned an invalid principal variation.")
        san_line.append(line_board.san(move))
        line_board.push(move)
    player_score = score.pov(board.turn)
    bound = "lower" if info.get("lowerbound") else "upper" if info.get("upperbound") else "exact"
    if score.turn != board.turn and bound != "exact":
        bound = "upper" if bound == "lower" else "lower"
    return {
        "rank": rank,
        "uci": pv[0].uci(),
        "san": san_line[0],
        "score": {"cp": player_score.score(), "mate": player_score.mate(), "bound": bound},
        "pv_uci": [move.uci() for move in pv],
        "pv_san": san_line,
        "depth": info["depth"],
    }


def analyze_move(review: MoveReview, settings: StockfishSettings | None = None) -> dict:
    """Top eight root moves plus the played move, always from the same FEN.

    This blocking function belongs in a worker thread when used by an async API.
    Each invocation owns its engine process, including cleanup on failure.
    """
    # Revalidate even when a caller constructed the dataclass directly.
    review = MoveReview.from_fen(review.position.fen, review.played_move_uci)
    settings = settings or StockfishSettings.from_env()
    executable = settings.executable()
    board = chess.Board(review.position.fen)
    played = chess.Move.from_uci(review.played_move_uci)
    count = min(8, board.legal_moves.count())
    limit = chess.engine.Limit(depth=settings.depth, time=settings.time_limit)
    try:
        with chess.engine.SimpleEngine.popen_uci(executable, timeout=5.0) as engine:
            engine.configure({"Threads": settings.threads, "Hash": settings.hash_mb})
            infos = engine.analyse(board, limit, multipv=count)
            top_moves = [_candidate(board, info, rank) for rank, info in enumerate(infos, 1)]
            if len(top_moves) != count or len({item["uci"] for item in top_moves}) != count:
                raise StockfishAnalysisError("Stockfish did not return all requested candidate moves.")
            played_result = next((item for item in top_moves if item["uci"] == played.uci()), None)
            in_top_moves = played_result is not None
            if played_result is None:
                # Restrict the root search, rather than evaluating the child
                # board with its opposite side-to-move and a shifted depth.
                info = engine.analyse(board, limit, root_moves=[played])
                played_result = _candidate(board, info, None)
                if played_result["uci"] != played.uci():
                    raise StockfishAnalysisError("Stockfish evaluated a different played move.")
            return {
                "engine": engine.id.get("name", "Stockfish"),
                "perspective": review.position.side_to_move,
                "limits": {"depth": settings.depth, "seconds_per_search": settings.time_limit},
                "threads": settings.threads,
                "hash_mb": settings.hash_mb,
                "top_moves": top_moves,
                "played_move": played_result,
                "played_move_in_top": in_top_moves,
            }
    except TimeoutError as exc:
        raise StockfishTimeoutError("Stockfish exceeded its response deadline.") from exc
    except OSError as exc:
        raise StockfishUnavailableError("Stockfish could not be started. Check its installation and permissions.") from exc
    except chess.engine.EngineError as exc:
        raise StockfishAnalysisError("Stockfish could not complete the analysis.") from exc


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    parser = argparse.ArgumentParser(description="Prepare a move review with local Stockfish; no model calls.")
    parser.add_argument("--fen", required=True)
    parser.add_argument("--move", required=True, help="Played move in UCI, for example e2e4.")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        review = MoveReview.from_fen(args.fen, args.move)
        print(json.dumps({**review.as_dict(), "stockfish": analyze_move(review)}, indent=2))
    except (InvalidPositionError, StockfishUnavailableError, StockfishAnalysisError) as exc:
        print(f"Move review: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
