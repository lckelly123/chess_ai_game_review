# Chess study

A local game library and replay workspace built with React, TypeScript, FastAPI, and PostgreSQL. Import completed standard-chess games from a public Chess.com username, search and filter your library, and replay positions on the board. Run coach requests position analysis from OpenAI and saves it for future replay visits. Engine analysis is outside this version.

## Run with Docker

Start Docker Desktop with Linux containers. For a fresh checkout, copy `.env.example` to `.env` and set a nonempty `POSTGRES_PASSWORD`. Keep that password when reusing the database volume. Then from the repository root:

```sh
docker compose up --build -d
```

Open **http://localhost:8000**. Enter a Chess.com username and import the latest 20, 50, or 100 games. No Chess.com password or API key is needed. The username is a public lookup, not verified ownership or account linking.

```sh
docker compose logs -f app
docker compose down
```

Games and coach feedback are stored in PostgreSQL's `postgres-data` named volume and survive ordinary container recreation and `docker compose down`. **`docker compose down -v` deletes the named volumes.** PostgreSQL is reachable only on the Compose network by default. The opening screen is the game library. The frontend remembers the selected player and each game's replay position in the browser. This is a single-user local application: the app port binds to loopback by default, and there is no app authentication. Do not expose it publicly without adding access controls.

Set `PORT` or a descriptive `CHESSCOM_USER_AGENT` in `.env` as needed. The `db` service runs PostgreSQL 18; the app waits for its health check before starting.

### Existing SQLite installations

On the first PostgreSQL startup, the app imports games, profiles, profile associations, and HTTP cache records from the old `chess-data` volume. That volume is mounted read-only at `/legacy`; it is retained unchanged. The import and its `legacy_sqlite_v1` marker commit in one transaction. Failures roll back, and restarts do not overwrite migrated records. The migration reads a temporary copy of the offline SQLite database and any WAL/journal files, allowing SQLite to rebuild its shared-memory index without writing to the legacy volume. For a local SQLite file, stop its old app first, then set `LEGACY_SQLITE_PATH` to its absolute path when starting the Python backend. Old feedback that existed only in browser memory was never in SQLite; new coach runs are persisted.

### Stored coaching

`coach_feedback` contains the complete six-field FEN, Markdown answer, model, OpenAI response ID, token usage, and creation timestamp. Every successful run adds a row, preserving earlier versions. The replay loads the latest answer for each exact FEN automatically, including after a refresh, another visit, or a container restart. Matching includes side to move, castling and en-passant rights, and the move counters. No new OpenAI call is made merely to read saved coaching. Student question drafts still remain in browser storage only.

For a SQL session inside Docker:

```sh
docker compose exec db psql -U chess -d chess_study
```

## Development on Windows

Python 3.13+ and Node.js 22.12+ (or Node 24) are recommended. In one PowerShell terminal at the repository root:

```powershell
docker compose -f compose.yaml -f compose.dev.yaml up -d db
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.lock
.\.venv\Scripts\python -m uvicorn backend.main:app --reload
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open the Vite URL (normally http://127.0.0.1:5173). Vite proxies `/api` to the backend at port 8000. `compose.dev.yaml` exposes PostgreSQL on loopback port 5433. The `PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE`, and `PGPASSWORD` settings in `.env.example` connect a local Python process to it. `DATABASE_URL` can override these settings. Stop the Docker app before running a local backend on the same port. After `npm run build`, FastAPI also serves the compiled UI directly on port 8000.

## Replay

- Click **Analyze** beside a saved game to open its dedicated replay screen, then use the replay buttons and slider.
- **Back to games** returns to the library with your filters, scroll position, and keyboard focus restored. Browser Back/Forward and replay links also work.
- Left/right arrows step through moves; Home/End jump to the beginning/end; Space toggles autoplay. Shortcuts do not intercept form fields. Space retains its native action on focused buttons and links.
- Flip the board; the initial orientation follows the imported player.
- Download the original PGN or open the source game on Chess.com.
- Selecting a game again restores your last position in this browser.
- The Coach panel has a wide, scrollable response area with formatted headings, emphasis, and lists, plus a question box. Run coach analyzes the currently selected position and saves its answer to PostgreSQL. The latest saved answer is restored automatically. Question drafts are saved per game in this browser and are not sent.

## Coach backend

`backend/coach/` contains a LangGraph workflow using the OpenAI Responses API with GPT-6 Astra and xhigh reasoning. Its first node, `analyze_position`, validates a selected FEN, generates the matching ASCII board, and sends both with the supplied system prompt. The replay screen calls `POST /api/coach/analyze` when Run coach is pressed. Only the selected FEN is accepted; student questions are not connected.

See [backend/coach/README.md](backend/coach/README.md) for the Python interface, command-line dry run, credentials, and Docker usage. Set `OPENAI_API_KEY` in the ignored project `.env`, then restart the app (`docker compose up -d` for Docker). The key is used only by the backend. The existing game library works without a key.

The same graph is available in LangSmith Studio through the root `langgraph.json`. Install `backend/requirements-dev.txt`, set `$env:PYTHONUTF8 = "1"` on Windows, and run `.\.venv\Scripts\langgraph dev` from the root. See the coach README for Studio input and tracing setup. LangSmith tracing is optional: set `LANGSMITH_API_KEY`, `LANGSMITH_TRACING=true`, and `LANGSMITH_PROJECT=chess-coach` in `.env` to record graph, node, and Responses API spans. App requests execute the graph directly and do not require the Studio server.

## Import behavior

The backend reads the documented [Chess.com Published Data API](https://www.chess.com/news/view/published-data-api). Imports run in the background, one at a time, with progress polling. They inspect up to the latest 24 available archive months, newest first, stopping at the requested number of valid standard-chess games. Variants, unfinished games, and malformed PGNs are skipped and reported. Each import adds to the library and deduplicates using the source game URL; requesting the latest 100 expands the same recent window, not an older-history pagination cursor.

Requests are serial, cached for 15 minutes locally, and conditionally revalidated using ETag/Last-Modified. Rate limits and temporary errors receive bounded retries. Chess.com's own cache can delay new games longer. Imports are committed atomically; a failed import preserves the existing library. In-progress job status is held in memory and expires on server restart; repeating an interrupted import is safe. Run a single API worker for this local version so import coordination and progress stay in one process.

PostgreSQL stores original PGNs, JSONB metadata, profile associations, HTTP cache records, and coach feedback. The backend uses python-chess to reconstruct every position, including castling, en passant, promotions, and custom starting positions. The browser renders the returned positions; it does not maintain a second move-rule engine.

## Checks

```powershell
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f compose.test.yaml down
cd frontend
npm run build
```

The test stack uses a separate PostgreSQL container with temporary storage and no production credentials or OpenAI calls. Backend tests cover SQLite migration/rollback, feedback history and restart persistence, database failures, coach serialization/validation, imports, caching, replay, and the existing graph workflow. For local pytest, install `backend/requirements-dev.txt` and set `TEST_DATABASE_URL` to a disposable PostgreSQL database; tests create and remove isolated schemas there. `npm run build` performs TypeScript checking before bundling. Runtime Python dependencies are pinned in `backend/requirements.lock`; npm versions are pinned in `frontend/package-lock.json`.

## Project layout

- `backend/main.py`: API, import jobs, lifecycle, and static frontend serving.
- `backend/importer.py`: Chess.com client, caching, retries, and bounded imports.
- `backend/database.py` and `backend/schema.sql`: PostgreSQL persistence and tables.
- `backend/migrate_sqlite.py`: one-time, read-only migration of legacy data.
- `backend/chess_games.py`: source normalization and PGN replay.
- `frontend/src/`: library, board, replay, and styles.
- `backend/coach/`: extensible LangGraph coach, traced Responses adapter, prompt, validation, and CLI.
- `langgraph.json`: local Agent Server/Studio graph registration and environment configuration.

This project is independent of Chess.com. See `THIRD_PARTY_NOTICES.md` for dependency licensing. The future AI product needs a separate review of Chess.com's API guidance and AI-use terms; only pressing Run coach (or explicitly invoking the service/CLI) sends a selected position to OpenAI; student questions are not sent.
