"""Player/time-control summaries built only from persisted move evidence."""

from datetime import datetime, timezone

import chess
from psycopg import sql
from psycopg.types.json import Jsonb

from .coach.classification import CLASSIFICATION_VERSION

VERSION = 1
MOTIFS = ("hanging_piece", "fork", "pin_skewer", "discovered_attack")
CONTEXTS = ("Attack", "Defend", "Improve", "Convert")
PIECES = ("pawn", "knight", "bishop", "rook", "queen", "king")
OUTLOOKS = ("Losing", "Worse", "Equal", "Better", "Winning")
PHASES = ("opening", "middlegame", "endgame")
SHARPNESS = ("Forgiving", "Flexible", "Selective", "Demanding", "Critical")
ERRORS = {"Inaccuracy", "Mistake", "Blunder"}
GRADED = ERRORS | {"Best", "Excellent", "Good"}
TABLES = ("tactical", "decision_context", "piece_comparison", "context_outlook", "phase", "sharpness", "outlook")


def rate_counts(categories):
    return {f"{category.lower()}_{suffix}": 0 for category in categories for suffix in ("errors", "moves")}


def empty_summary():
    return {
        "tactical": {f"{motif}_{kind}": 0 for motif in MOTIFS for kind in ("missed", "allowed")},
        "decision_context": {f"{context.lower()}_count": 0 for context in CONTEXTS},
        "piece_comparison": {"counts": {piece: dict.fromkeys(PIECES, 0) for piece in PIECES}},
        "context_outlook": {"counts": {outlook: dict.fromkeys(CONTEXTS, 0) for outlook in OUTLOOKS}},
        "phase": rate_counts(PHASES),
        "sharpness": rate_counts(SHARPNESS),
        "outlook": rate_counts(OUTLOOKS),
    }


def position_outlook(move):
    """Rank-one scores are stored White-relative; classify the mover's outlook."""
    if move.get("top_1_bound") != "exact" or (move.get("top_1_depth") or 0) < 1:
        return None
    cp, mate = move.get("top_1_cp"), move.get("top_1_mate")
    sign = 1 if move["color"] == "white" else -1
    if type(mate) is int and cp is None:
        # A recorded decision cannot start at mate-in-zero.
        return ("Winning" if mate * sign > 0 else "Losing") if mate else None
    if type(cp) is not int or mate is not None:
        return None
    cp *= sign
    if cp < -300:
        return "Losing"
    if cp < -50:
        return "Worse"
    if cp <= 50:
        return "Equal"
    return "Better" if cp <= 300 else "Winning"


def preferred_piece(move):
    if move.get("top_1_bound") != "exact" or (move.get("top_1_depth") or 0) < 1:
        return None
    try:
        board = chess.Board(move["fen_before"])
        best = chess.Move.from_uci(move["top_1_uci"])
        if best not in board.legal_moves:
            return None
        return chess.piece_name(board.piece_type_at(best.from_square))
    except (ValueError, TypeError, KeyError):
        return None


def aggregate_moves(moves):
    """Every source row is one player decision; ungraded imports establish empty buckets."""
    groups = {}
    for move in moves:
        key = (move["time_class"], move["time_control_raw"])
        if key not in groups:
            groups[key] = empty_summary()
        summary = groups[key]
        if (move["engine_status"] != "completed" or move["engine_pgn_hash"] != move["pgn_hash"]
                or move["move_quality"] not in GRADED):
            continue
        error = move["move_quality"] in ERRORS
        outlook = position_outlook(move)
        for table, category, supported in (("phase", move["phase_before"], PHASES),
                ("sharpness", move["sharpness_classification"], SHARPNESS), ("outlook", outlook, OUTLOOKS)):
            if category in supported:
                summary[table][f"{category.lower()}_moves"] += 1
                summary[table][f"{category.lower()}_errors"] += int(error)
        # A grade alone never supplies a tactical motif or positional objective.
        if not error or move.get("classification_version") not in (2, 3, CLASSIFICATION_VERSION):
            continue
        category, subcategory = move["coach_error_category"], move["coach_error_subcategory"]
        if category in ("tactical_miss", "tactical_allowed") and subcategory in MOTIFS:
            kind = "missed" if category == "tactical_miss" else "allowed"
            summary["tactical"][f"{subcategory}_{kind}"] += 1
        elif category == "positional":
            # Older positional reviews may lack an objective; their known piece
            # pair still belongs in the heatmap, but no context is invented.
            if subcategory in CONTEXTS:
                summary["decision_context"][f"{subcategory.lower()}_count"] += 1
                if outlook:
                    summary["context_outlook"]["counts"][outlook][subcategory] += 1
            best = preferred_piece(move)
            played = move["piece_moved"]
            if played in PIECES and best in PIECES:
                summary["piece_comparison"]["counts"][played][best] += 1
    return groups


def refresh_games(db, game_ids, usernames=()):
    affected = set(usernames)
    affected.update(row["username"] for row in db.execute(
        "SELECT DISTINCT username FROM profile_games WHERE game_id=ANY(%s)", (list(game_ids),)))
    for username in sorted(affected):
        refresh_player(db, username)


def refresh_player(db, username):
    # Serialize rebuilds for this player before taking the single source snapshot.
    # Rebuilds read source rows without row locks; multi-player updates acquire
    # these advisory locks in sorted username order via refresh_games.
    db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("analytics:" + username,))
    moves = db.execute("""SELECT g.time_class,g.time_control_raw,g.pgn_hash,
        m.engine_status,m.engine_pgn_hash,m.move_quality,m.phase_before,m.sharpness_classification,
        m.color,m.piece_moved,m.fen_before,m.top_1_uci,m.top_1_cp,m.top_1_mate,m.top_1_bound,m.top_1_depth,
        m.coach_error_category,m.coach_error_subcategory,
        m.coach_metadata -> 'classification_version' AS classification_version
        FROM profile_games p JOIN games g USING(game_id) JOIN game_moves m USING(game_id)
        WHERE p.username=%s AND
            ((m.color='white' AND lower(g.white_username)=p.username)
             OR (m.color='black' AND lower(g.black_username)=p.username))""", (username,)).fetchall()
    groups = aggregate_moves(moves)
    now = datetime.now(timezone.utc)
    for name in TABLES:
        table = sql.Identifier("analytics_" + name)
        db.execute(sql.SQL("DELETE FROM {} WHERE username=%s").format(table), (username,))
        for (time_class, control), summary in sorted(groups.items()):
            row = {"username": username, "time_class": time_class, "time_control_raw": control,
                   **summary[name], "calculation_version": VERSION, "updated_at": now}
            db.execute(sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(table,
                sql.SQL(",").join(map(sql.Identifier, row)), sql.SQL(",").join(sql.Placeholder() for _ in row)),
                [Jsonb(v) if isinstance(v, dict) else v for v in row.values()])
    return read_player(db, username)


def read_player(db, username):
    groups, timestamps = {}, []
    for name in TABLES:
        rows = db.execute(sql.SQL("SELECT * FROM {} WHERE username=%s").format(
            sql.Identifier("analytics_" + name)), (username,)).fetchall()
        for row in rows:
            key = (row["time_class"], row["time_control_raw"])
            group = groups.setdefault(key, {"time_class": key[0], "time_control_raw": key[1]})
            group[name] = {k: v for k, v in row.items() if k not in
                ("username", "time_class", "time_control_raw", "updated_at", "calculation_version")}
            timestamps.append(row["updated_at"])
    return {"username": username, "calculation_version": VERSION,
            "updated_at": max(timestamps) if timestamps else None,
            "time_controls": [groups[key] for key in sorted(groups)]}
