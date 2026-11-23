"""Read-only lesson analytics over a player's saved game decisions."""

from .chess_games import replay
from .coach.classification import lesson_classification
from .coach.player_move_quality import with_player_move_quality
from .game_analysis import pgn_fingerprint

SEVERITIES = ("inaccuracy", "mistake", "blunder")
TACTICAL_MOTIFS = (
    ("hanging_piece", "Hanging piece"), ("fork", "Fork"),
    ("pin_skewer", "Pin / skewer"), ("discovered_attack", "Discovered attack"),
)
LESSON_CATEGORIES = (
    ("tactical_miss", "Missed tactics", TACTICAL_MOTIFS),
    ("tactical_allowed", "Allowed tactics", TACTICAL_MOTIFS),
    ("positional", "Positional", tuple((piece, piece.title()) for piece in
        ("pawn", "knight", "bishop", "rook", "queen", "king"))),
)


def empty_counts():
    return {**{severity: 0 for severity in SEVERITIES}, "total": 0}


def increment(counts, severity):
    counts[severity] += 1
    counts["total"] += 1


def lesson_analytics(database, username: str) -> dict:
    """Count a game/ply once, using its saved grade and latest matching review.

    Feedback is shared by FEN and move, so counting feedback rows would inflate
    reruns and lose repeated decisions played in separate games. Instead, start
    with this player's current game analyses and attach the latest saved label.
    """
    username = username.strip().lower()
    categories = [
        {"key": key, "label": label, "counts": empty_counts(), "subcategories": [
            {"key": subkey, "label": sublabel, "counts": empty_counts()}
            for subkey, sublabel in subcategories
        ]}
        for key, label, subcategories in LESSON_CATEGORIES
    ]
    buckets = {(category["key"], row["key"]): row["counts"]
               for category in categories for row in category["subcategories"]}
    category_counts = {category["key"]: category["counts"] for category in categories}
    result = {"username": username, "imported_games": 0, "analyzed_games": 0, "analyzed_moves": 0,
              "errors": empty_counts(), "categories": categories, "unclassified": empty_counts(),
              "pending_reviews": 0, "outdated_reviews": 0}
    imported_games, analyzed_games, seen = set(), set(), set()
    errors = []
    for record in database.lesson_games(username):
        color = next((color for color in ("white", "black")
                      if record["metadata"].get(color, "").lower() == username), None)
        if color is None:
            continue
        imported_games.add(record["id"])
        if record.get("pgn_hash") != pgn_fingerprint(record["pgn"]) or not record.get("moves"):
            continue
        try:
            detail = replay(record["pgn"])
        except ValueError:
            continue
        for key, saved in record["moves"].items():
            if not key.isdecimal():
                continue
            ply = int(key)
            occurrence = (record["id"], ply)
            if str(ply) != key or ply >= len(detail["moves"]) or occurrence in seen:
                continue
            move = detail["moves"][ply]
            fen = detail["positions"][ply]["fen"]
            if (move["color"] != color or saved.get("fen") != fen
                    or saved.get("played_move") != move["uci"]):
                continue
            evidence = saved.get("stockfish")
            if (not isinstance(evidence, dict) or evidence.get("fen") != fen
                    or evidence.get("perspective") != color.title()
                    or evidence.get("played_move", {}).get("uci") != move["uci"]):
                continue
            seen.add(occurrence)
            analyzed_games.add(record["id"])
            result["analyzed_moves"] += 1
            severity = with_player_move_quality(evidence)["move_quality"]["status"]
            if severity in SEVERITIES:
                errors.append((fen, move["uci"], severity))

    reviews = database.coach_feedback_for_reviews(list(dict.fromkeys((fen, move) for fen, move, _ in errors)))
    for fen, move, severity in errors:
        increment(result["errors"], severity)
        review = reviews.get((fen, move))
        teaching = (review or {}).get("teaching") or {}
        evaluation = teaching.get("move_evaluation") or {}
        classification = evaluation.get("mistake_classification")
        bucket = (classification.get("category"), classification.get("subcategory")) if isinstance(classification, dict) else None
        if lesson_classification(review) and bucket in buckets:
            increment(buckets[bucket], severity)
            increment(category_counts[bucket[0]], severity)
        else:
            increment(result["unclassified"], severity)
        if review and not lesson_classification(review):
            result["outdated_reviews"] += 1
        elif not review:
            result["pending_reviews"] += 1
    result.update(imported_games=len(imported_games), analyzed_games=len(analyzed_games))
    return result
