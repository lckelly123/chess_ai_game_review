"""Run with python -m backend.coach --fen '...' [--dry-run]."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from openai import APIConnectionError, APIStatusError, APITimeoutError

from .position import CoachPosition, InvalidPositionError
from .move_review import MoveReview
from .stockfish import StockfishAnalysisError, StockfishUnavailableError
from .service import CoachResponseError, build_request, open_coach
from .settings import CoachConfigurationError, CoachSettings


async def run(args: argparse.Namespace) -> None:
    settings = CoachSettings.from_env()
    ascii_board = Path(args.ascii_file).read_text(encoding="utf-8") if args.ascii_file else None
    # Validate locally before opening a client; dry runs never require a key.
    CoachPosition.from_fen(args.fen, ascii_board=ascii_board)
    if args.move is not None:
        MoveReview.from_fen(args.fen, args.move)
    if args.dry_run:
        request = await asyncio.to_thread(build_request, args.fen, ascii_board=ascii_board, settings=settings)
        print(json.dumps(request, indent=2, ensure_ascii=False))
        return
    async with open_coach(settings) as coach:
        result = await coach.analyze(args.fen, ascii_board=ascii_board, played_move=args.move)
        print(result.text)


def main() -> int:
    # Keep Markdown (including arrows in the system prompt) intact in Windows pipes.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Coach one chess position with GPT-6 Astra (medium reasoning).")
    parser.add_argument("--fen", required=True, help="Complete six-field FEN of the selected position.")
    parser.add_argument("--ascii-file", help="Optional matching ASCII board; otherwise generated from the FEN.")
    parser.add_argument("--move", help="Optional recorded move in UCI; enables the second coaching pass.")
    parser.add_argument("--dry-run", action="store_true", help="Run local Stockfish and print the first-pass request without calling OpenAI.")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except (InvalidPositionError, CoachConfigurationError, CoachResponseError, StockfishUnavailableError, StockfishAnalysisError, OSError) as exc:
        print(f"Coach: {exc}", file=sys.stderr)
        return 1
    except APITimeoutError:
        print("Coach: OpenAI timed out. No automatic retry was made.", file=sys.stderr)
        return 1
    except APIConnectionError:
        print("Coach: Could not connect to OpenAI. Check the connection and try again.", file=sys.stderr)
        return 1
    except APIStatusError as exc:
        print(f"Coach: OpenAI returned HTTP {exc.status_code}. Check API credentials, model access, or quota. Request ID: {exc.request_id or 'unavailable'}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
