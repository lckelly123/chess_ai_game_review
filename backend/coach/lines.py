"""Legal board playback from saved engine evidence, with no additional searches."""

import chess


def move_lines(fen: str, moves: dict[str, dict]) -> dict:
    lines = {}
    for uci, evidence in moves.items():
        pv = evidence.get("pv_uci") or []
        if not isinstance(pv, list) or not pv or pv[0] != uci:
            continue
        board = chess.Board(fen)
        positions = [{"fen": fen, "last_move": None,
                      "check_square": chess.square_name(board.king(board.turn)) if board.is_check() else None}]
        names = []
        for value in pv:
            try:
                move = chess.Move.from_uci(value)
                if move not in board.legal_moves:
                    break
            except (ValueError, TypeError):
                break
            names.append(board.san(move))
            board.push(move)
            positions.append({"fen": board.fen(en_passant="fen"),
                              "last_move": [chess.square_name(move.from_square), chess.square_name(move.to_square)],
                              "check_square": chess.square_name(board.king(board.turn)) if board.is_check() else None})
        if names:
            lines[uci] = {"san": names, "positions": positions}
    return lines
