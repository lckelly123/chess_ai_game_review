import hashlib
import io
import logging
from urllib.parse import urlparse

import chess
import chess.pgn

# python-chess logs parsing errors itself; the importer reports skipped games.
logging.getLogger("chess.pgn").setLevel(logging.CRITICAL)


def parse_game(pgn: str) -> chess.pgn.Game:
    if not pgn.strip() or len(pgn) > 500_000:
        raise ValueError("Game has no usable PGN.")
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None or game.errors or not game.board().is_valid() or game.headers.get("Variant", "Standard") not in ("Standard", "Chess"):
        raise ValueError("Game contains invalid or unsupported moves.")
    return game


def normalize_game(raw: dict, username: str) -> dict:
    if raw.get("rules") != "chess":
        raise ValueError("Only standard chess is supported.")
    url = raw["url"]
    parsed_url = urlparse(url)
    if parsed_url.scheme != "https" or parsed_url.hostname not in {"www.chess.com", "chess.com"}:
        raise ValueError("Invalid source game URL.")
    game = parse_game(raw["pgn"])
    if game.headers.get("Result") not in {"1-0", "0-1", "1/2-1/2"}:
        raise ValueError("Only completed games are supported.")
    white, black = raw["white"], raw["black"]
    if username not in {white["username"].lower(), black["username"].lower()}:
        raise ValueError("Game does not belong to this player.")
    moves = list(game.mainline_moves())
    if not moves:
        raise ValueError("Game has no moves to replay.")
    return {
        "id": hashlib.sha256(url.encode()).hexdigest()[:24],
        "url": url, "pgn": raw["pgn"],
        "white": white["username"], "black": black["username"],
        "white_rating": white.get("rating"), "black_rating": black.get("rating"),
        "result": game.headers["Result"],
        "end_time": int(raw["end_time"]),
        "time_class": raw.get("time_class", "unknown"),
        "time_control": raw.get("time_control", ""),
        "opening": game.headers.get("Opening", ""),
        "eco": game.headers.get("ECO", ""),
        "ply_count": len(moves),
    }


def replay(pgn: str) -> dict:
    game = parse_game(pgn)
    board = game.board()
    positions = [{"fen": board.fen(), "last_move": None, "check_square": chess.square_name(board.king(board.turn)) if board.is_check() else None}]
    moves = []
    for index, move in enumerate(game.mainline_moves(), start=1):
        moves.append({"ply": index, "san": board.san(move), "uci": move.uci(), "color": "white" if board.turn else "black", "number": board.fullmove_number})
        board.push(move)
        positions.append({"fen": board.fen(), "last_move": [chess.square_name(move.from_square), chess.square_name(move.to_square)], "check_square": chess.square_name(board.king(board.turn)) if board.is_check() else None})
    return {"positions": positions, "moves": moves}
