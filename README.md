# Chess study

A local game library and replay workspace built with React, TypeScript, FastAPI, and PostgreSQL. Import completed standard-chess games from a public Chess.com username, search and filter your library, and replay positions on the board. Run coach explains the position and plan, then evaluates the next recorded move using Stockfish evidence. Both passes are saved for future visits and displayed in two tabs within one coach response panel.

## Run with Docker

Start Docker Desktop with Linux containers. For a fresh checkout, copy `.env.example` to `.env` and set a nonempty `POSTGRES_PASSWORD`. Keep that password when reusing the database volume. Then from the repository root:

```sh
docker compose up --build -d
```

Open **http://localhost:8000**. Enter a Chess.com username and import the latest 20, 50, or 100 games. No Chess.com password or API key is needed. The username is a public lookup, not verified ownership or account linking.

The same command also starts the **Studio graph server** on http://127.0.0.1:2024. Open [LangSmith Studio](https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024) and select **chess_coach** to visualize and run the graph. The `app` and `studio` services use the same image, including Python, graph dependencies, and Stockfish; no local `.venv` or additional startup command is needed. Both services can also be started from the existing Compose stack in Docker Desktop after the first build. See [Studio inputs and tracing setup](backend/coach/README.md#run-in-langsmith-studio).

```sh
docker compose logs -f app
docker compose logs -f studio
docker compose down
```

Games and coach feedback are stored in PostgreSQL's `postgres-data` named volume and survive ordinary container recreation and `docker compose down`. **`docker compose down -v` deletes the named volumes.** PostgreSQL is reachable only on the Compose network by default. The opening screen is the game library. The frontend remembers the selected player and each game's replay position in the browser. This is a single-user local application: the app port binds to loopback by default, and there is no app authentication. Do not expose it publicly without adding access controls.

Set `PORT`, `STUDIO_PORT`, or a descriptive `CHESSCOM_USER_AGENT` in `.env` as needed. Both published ports bind to loopback; if you change `STUDIO_PORT`, use that port in Studio's `baseUrl`. The `db` service runs PostgreSQL 18; the app waits for its health check before starting. Studio starts independently of the app/database and keeps its development threads and checkpoints in the separate `studio-data` volume, which survives ordinary restarts and `docker compose down`. Rebuild with the usual command after code or dependency changes so both services use the same updated graph.

### Existing SQLite installations

On the first PostgreSQL startup, the app imports games, profiles, profile associations, and HTTP cache records from the old `chess-data` volume. That volume is mounted read-only at `/legacy`; it is retained unchanged. The import and its `legacy_sqlite_v1` marker commit in one transaction. Failures roll back, and restarts do not overwrite migrated records. The migration reads a temporary copy of the offline SQLite database and any WAL/journal files, allowing SQLite to rebuild its shared-memory index without writing to the legacy volume. For a local SQLite file, stop its old app first, then set `LEGACY_SQLITE_PATH` to its absolute path when starting the Python backend. Old feedback that existed only in browser memory was never in SQLite; new coach runs are persisted.

### Stored coaching

`coach_feedback` contains the complete six-field FEN, played move in UCI, combined Markdown answer, both passes' text/model/response IDs/token usage, Stockfish evidence, and creation timestamp. Every successful run adds a row, preserving earlier versions. The replay loads the latest answer for each exact FEN plus played move, including after a refresh or restart. Position-only answers use an empty move internally; existing feedback is preserved by an additive schema upgrade and remains visible until a move review replaces it for that position. Failed second passes do not save a partial review or erase an earlier answer. No new OpenAI call is made merely to read saved coaching. Student question drafts remain in browser storage only.

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

### Stockfish and move review

Docker builds install the checksum-pinned official Stockfish 19 release automatically. Rebuild with `docker compose up --build -d` to include it; no separate Windows engine installation is needed when the backend runs in Docker.

The preparation endpoint `POST /api/coach/prepare-move` accepts `{ "game_id": "<saved game ID>", "ply": 0 }`. `ply` is the number of half-moves already played, shown by the replay counter: position 0 reviews White's first move, position 1 reviews Black's reply. The slider selects player decision points and maps them to these original half-move indexes. The server derives the pre-move FEN, ASCII board, and next recorded move from the saved PGN. The final recorded position returns 422 because there is no next move, including games that ended by resignation or agreement. Explore the endpoint at http://localhost:8000/docs.

It returns the validated move in UCI and SAN, a key derived from the complete FEN plus move, and Stockfish's top eight legal candidates (or fewer when fewer legal moves exist). The played move is evaluated separately from the same root position only when it is absent from the eight. Scores are from the side-to-move player's perspective, with centipawns and mate scores kept separate; principal variations and achieved search depths accompany the scores. The default search stops at depth 18 or 10 seconds per search, with two threads and 128 MB hash. Configure these limits through the `STOCKFISH_*` settings in `.env.example`.

The preparation endpoint makes no OpenAI calls and does not save feedback. Run coach uses the same engine adapter inside the second LangGraph node and makes two Responses API calls when a next move exists. At the final recorded position, Run coach performs only the position analysis. Engine analysis currently uses the supplied FEN without earlier repetition history.

For a locally running Windows Python backend, install the engine once:

```powershell
.\.venv\Scripts\python scripts\install_stockfish.py
```

The backend discovers the ignored `.tools/stockfish` installation automatically. Alternatively, set `STOCKFISH_PATH` to an existing engine executable. A standalone engine check works without an OpenAI key or a database:

```powershell
.\.venv\Scripts\python -m backend.coach.stockfish --fen "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1" --move e2e4
```

In Docker, use `docker compose exec app python -m backend.coach.stockfish` with the same `--fen` and `--move` arguments. This CLI loads `.env` for local engine settings.

### Replay controls

- Click **Analyze** beside a saved game to open its dedicated replay screen, then use the replay buttons and slider.
- **Back to games** returns to the library with your filters, scroll position, and keyboard focus restored. Browser Back/Forward and replay links also work.
- Left/right arrows stop on the imported player's turns, briefly showing the intervening position for 100 ms. Black's first forward step advances only White's opening move. Backward navigation follows the same rule. Home/End keep the starting and final positions reachable even when the opponent is to move.
- The slider selects the same decision points; Space toggles autoplay through them. Reduced-motion preference skips the intermediate board. Shortcuts do not intercept form fields or the coach cards. Space retains its native action on focused buttons and links.
- Flip the board; the initial orientation follows the imported player.
- Selecting a game again restores your last settled position in this browser. Older bookmarks on an opponent's turn move back to the preceding player decision.
- The Coach response has two tabs in one box: Position & plan combines analysis, needs, and recommended moves; Evaluate your move contains engine scores and the move review. The selected tab stays active while navigating positions or rerunning coaching. Arrow keys and Home/End switch focused tabs. Content follows the settled position without flashing opponent feedback during a turn transition. Run coach analyzes the currently selected position and saves its answer to PostgreSQL. The latest saved answer is restored automatically. Select a candidate move to show its arrow and two instructional squares without playing it; selecting pauses autoplay. Clear removes the overlay, and navigation or a new response resets it. The move-review tab hides candidate overlays; returning to Position & plan restores the current selection. Older saved reviews retain their content in the same tabs; rerun coaching to generate the new structured teaching and candidate annotations. Question drafts are saved per game in this browser and are not sent.

## Coach backend

`backend/coach/` contains a LangGraph workflow using the OpenAI Responses API with GPT-6 Astra (default, medium reasoning) or GPT-6.1 Terra (medium reasoning). The selected model’s reasoning effort applies to both passes. Choose the model beneath Run coach; the browser remembers the selection. Both models use the same prompts, engine evidence, and graph. `analyze_position` receives only the selected FEN and derived ASCII board. `evaluate_move` receives its complete output, the same board, the next recorded move, and Stockfish's candidates and played-move evaluation, using the separate supplied move-review prompt. The first node uses strict structured output: position character, concise thesis, needs, and one to three legal instructional candidates (empty only when no legal moves exist). Candidates and their two highlight squares are validated before the second node. Its section 3 remains Markdown and is appended to a readable rendering of the first response. Structured data is retained in the existing JSONB storage and returned as `teaching`, with server-derived `candidate_san` labels. The replay sends `{ "game_id": "...", "ply": 0, "model": "gpt-6.1-terra" }` to `POST /api/coach/analyze`; the server derives the position and move from the saved PGN. `{ "fen": "...", "model": "gpt-6.1-terra" }` remains available for position-only coaching. Omitting `model` defaults to Astra; unsupported model IDs are rejected. Saved responses identify their generating model; selecting another model takes effect on the next run. Student questions are not connected.

See [backend/coach/README.md](backend/coach/README.md) for the Python interface, command-line dry run, credentials, and Docker usage. Set `OPENAI_API_KEY` in the ignored project `.env`, then restart the app (`docker compose up -d` for Docker). The key is used only by the backend. The existing game library works without a key.

The same graph is available in LangSmith Studio through the root `langgraph.json`; Docker Compose starts its server automatically. See the coach README for Studio input, tracing setup, and optional local Python development. LangSmith tracing is optional: set `LANGSMITH_API_KEY`, `LANGSMITH_TRACING=true`, and `LANGSMITH_PROJECT=chess-coach` in `.env`, then run `docker compose up -d` to apply those settings to both services and record graph, node, and Responses API spans. App requests execute the graph directly and do not require the Studio server.

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

The test stack uses a separate PostgreSQL container with temporary storage and no production credentials or OpenAI calls. Backend tests cover SQLite migration/rollback, feedback history and restart persistence, database failures, coach serialization/validation, imports, caching, replay, and the existing graph workflow. For local pytest, install `backend/requirements-dev.txt` and set `TEST_DATABASE_URL` to a disposable PostgreSQL database; tests create and remove isolated schemas there. `npm run build` performs TypeScript checking before bundling. App Python dependencies are pinned in `backend/requirements.lock`, and `backend/requirements-studio.txt` adds pinned Studio CLI/API/runtime versions; npm versions are pinned in `frontend/package-lock.json`.

## Project layout

- `backend/main.py`: API, import jobs, lifecycle, and static frontend serving.
- `backend/importer.py`: Chess.com client, caching, retries, and bounded imports.
- `backend/database.py` and `backend/schema.sql`: PostgreSQL persistence and tables.
- `backend/migrate_sqlite.py`: one-time, read-only migration of legacy data.
- `backend/chess_games.py`: source normalization and PGN replay.
- `frontend/src/`: library, board, replay, and styles.
- `backend/coach/`: extensible LangGraph coach, traced Responses adapter, prompt, validation, and CLI.
- `langgraph.json`: local Agent Server/Studio graph registration and environment configuration.

This project is independent of Chess.com. See `THIRD_PARTY_NOTICES.md` for dependency licensing. The future AI product needs a separate review of Chess.com's API guidance and AI-use terms; only pressing Run coach (or explicitly invoking the service/CLI) sends the selected position and, when available, the played move and engine evidence to OpenAI; student questions are not sent.
