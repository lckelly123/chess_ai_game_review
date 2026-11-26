"""Public, serial Chess.com access, isolated from storage and replay."""
import asyncio
import json
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

from .chess_games import normalize_game
from .database import Database

API = "https://api.chess.com/pub/player"


class ImportFailure(Exception):
    pass


class ChessComImporter:
    def __init__(self, database: Database, client: httpx.AsyncClient):
        self.db, self.client = database, client
        self.lock = asyncio.Lock()

    async def get(self, url: str, *, revalidate: bool = False) -> dict:
        cached = self.db.cache(url)
        if cached and not revalidate and time.time() - cached["fetched"] < 900:
            return json.loads(cached["body"])
        headers = {}
        if cached:
            if cached["etag"]:
                headers["If-None-Match"] = cached["etag"]
            if cached["modified"]:
                headers["If-Modified-Since"] = cached["modified"]
        for attempt in range(3):
            try:
                response = await self.client.get(url, headers=headers)
            except httpx.RequestError as exc:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ImportFailure("Could not reach Chess.com. Check your connection and try again.") from exc
            if response.status_code == 304 and cached:
                body = json.loads(cached["body"])
                self.db.save_cache(url, body, cached["etag"], cached["modified"], time.time())
                return body
            if response.status_code in (404, 410):
                raise ImportFailure("This Chess.com player or archive could not be found. Check the username.")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    delay = 2 ** attempt
                    retry = response.headers.get("Retry-After")
                    if retry:
                        try:
                            delay = float(retry)
                        except ValueError:
                            try:
                                delay = (parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds()
                            except (ValueError, TypeError):
                                pass
                    # Don't retry before a long server-requested backoff.
                    if delay > 15:
                        raise ImportFailure("Chess.com is busy. Please try again in a few minutes.")
                    await asyncio.sleep(max(0, delay))
                    continue
                raise ImportFailure("Chess.com is busy or temporarily unavailable. Try again in a few minutes.")
            if response.status_code != 200:
                raise ImportFailure("Chess.com declined the request. Please try again later.")
            try:
                body = response.json()
                if not isinstance(body, dict):
                    raise ValueError()
            except ValueError as exc:
                raise ImportFailure("Chess.com returned an unreadable response. Please try again later.") from exc
            self.db.save_cache(url, body, response.headers.get("ETag"), response.headers.get("Last-Modified"), time.time())
            return body
        raise ImportFailure("Import could not finish.")

    async def run(self, username: str, limit: int, job: dict, *, sync: bool = False):
        async with self.lock:
            job.update(status="running", message="Finding your Chess.com games…")
            try:
                await self.get(f"{API}/{username}", revalidate=sync)
                archive_data = await self.get(f"{API}/{username}/games/archives", revalidate=sync)
                archives = archive_data.get("archives")
                if not isinstance(archives, list):
                    raise ImportFailure("Chess.com returned an invalid archive list. Please try again later.")
                months = set()
                for url in archives:
                    # Never follow arbitrary URLs supplied by an upstream response.
                    match = re.fullmatch(r"https://api\.chess\.com/pub/player/[A-Za-z0-9_-]+/games/(\d{4})/(0[1-9]|1[0-2])", str(url))
                    if match:
                        months.add(f"{match[1]}/{match[2]}")
                window = self.db.game_sync_window(username) if sync else {"oldest": None, "newest": None, "last_synced": None}
                since = window["newest"] if window["newest"] is not None else window["last_synced"]
                catching_up = since is not None
                archive_months = sorted(months, reverse=True)
                if catching_up:
                    # Revisit the boundary month and its predecessor for delayed
                    # publication around a month rollover, then every newer month.
                    boundary = datetime.fromtimestamp(since, timezone.utc).replace(day=1)
                    first_month = (boundary - timedelta(days=1)).strftime("%Y/%m")
                    if window["oldest"] is not None:
                        # Older months cannot contribute games within the saved
                        # history boundary, and an unavailable one can block sync.
                        oldest_month = datetime.fromtimestamp(window["oldest"], timezone.utc).strftime("%Y/%m")
                        first_month = max(first_month, oldest_month)
                    archive_months = [month for month in archive_months if month >= first_month]
                else:
                    archive_months = archive_months[:24]
                selected, seen, skipped = [], set(), 0
                for month in archive_months:
                    job["message"] = f"Reading games from {month.replace('/', ' / ')}…"
                    data = await self.get(f"{API}/{username}/games/{month}", revalidate=sync)
                    raw_games = data.get("games")
                    if not isinstance(raw_games, list):
                        raise ImportFailure("Chess.com returned an invalid game archive. Please try again later.")
                    for raw in sorted(raw_games, key=lambda g: g.get("end_time", 0) if isinstance(g, dict) else 0, reverse=True):
                        if not isinstance(raw, dict) or raw.get("rules") != "chess":
                            skipped += 1
                            continue
                        try:
                            game = normalize_game(raw, username)
                        except (ValueError, KeyError, TypeError, AttributeError):
                            skipped += 1
                            continue
                        if game["id"] in seen:
                            continue
                        # Keep the original library's history boundary. Catch-up
                        # has no count limit, even after a long absence.
                        if catching_up and window["oldest"] is not None and game["end_time"] < window["oldest"]:
                            continue
                        selected.append(game)
                        seen.add(game["id"])
                        if not catching_up and len(selected) >= limit:
                            break
                    job["found"] = len(selected)
                    if not catching_up and len(selected) >= limit:
                        break
                added = self.db.save_import(username, selected, int(time.time()))
                message = f"Imported {added} new {'game' if added == 1 else 'games'}. {len(selected) - added} already in your library."
                if sync:
                    message = f"Added {added} new {'game' if added == 1 else 'games'}." if added else "No new games found."
                if not selected:
                    message = "No completed standard-chess games found in the most recent 24 archive months."
                job.update(status="completed", added=added, skipped=skipped, message=message)
            except ImportFailure as exc:
                job.update(status="failed", message=str(exc))
            except Exception:
                import logging
                logging.exception("Chess.com import failed")
                job.update(status="failed", message="The import could not finish. Your saved games are unchanged. Please try again.")
