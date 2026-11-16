"""One-time, atomic import from the previous SQLite store; never modifies it."""
import json
import logging
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from psycopg.types.json import Jsonb

from .database import Database

MIGRATION = "legacy_sqlite_v1"


@contextmanager
def legacy_snapshot(path: Path):
    """Copy an offline source including its WAL; SQLite may rebuild SHM here.

    Docker stops the old app before attaching its volume read-only. A local
    migration likewise requires stopping the old SQLite process first.
    """
    with TemporaryDirectory(prefix="chess-sqlite-") as directory:
        snapshot = Path(directory) / "chess.db"
        shutil.copyfile(path, snapshot)
        for suffix in ("-wal", "-journal"):
            journal = Path(str(path) + suffix)
            if journal.is_file():
                shutil.copyfile(journal, Path(str(snapshot) + suffix))
        db = sqlite3.connect(snapshot)
        try:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            yield db
        finally:
            db.close()


def migrate_sqlite(database: Database, source: str | Path) -> dict[str, int]:
    path = Path(source).resolve()
    if not path.is_file():
        return {}
    with database.connection() as target:
        target.execute("SELECT pg_advisory_xact_lock(7420918002)")
        if target.execute("SELECT 1 FROM schema_migrations WHERE name=%s", (MIGRATION,)).fetchone():
            return {}
        # All recovery/checkpoint writes happen in the disposable copy.
        with legacy_snapshot(path) as source_db:
            counts = {}
            for table, columns in (
                ("profiles", ("username", "last_synced")),
                ("games", ("id", "url", "pgn", "metadata", "end_time")),
                ("profile_games", ("username", "game_id")),
                ("http_cache", ("url", "body", "etag", "modified", "fetched")),
            ):
                # Table and column names are fixed above, never user input.
                rows = source_db.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
                for row in rows:
                    values = [Jsonb(json.loads(row[column])) if column == "metadata" else row[column] for column in columns]
                    target.execute(
                        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))}) ON CONFLICT DO NOTHING",
                        values,
                    )
                counts[table] = len(rows)
            target.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (MIGRATION,))
    logging.getLogger(__name__).info("Migrated legacy SQLite records to PostgreSQL: %s", counts)
    return counts
