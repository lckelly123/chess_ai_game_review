# Chess study

A local game library and replay workspace built with React, TypeScript, FastAPI, and PostgreSQL. Import completed standard-chess games from a public Chess.com username, search and filter your library, and replay positions on the board. Run coach combines position teaching, candidate moves, and feedback on the next recorded move in one card using Stockfish evidence. One model response is generated and saved for future visits.

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

`coach_feedback` stores the complete FEN, played move, combined coaching card, model/response ID/usage, and Stockfish evidence. Every successful run adds a row. The replay restores the latest exact FEN-plus-move response after refresh or restart. Failed runs leave prior feedback intact. Older reviews remain stored; rerun coaching to generate the new combined card. Reading saved feedback makes no OpenAI call.

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

The preparation endpoint makes no OpenAI calls and does not save feedback. Run coach uses a single LangGraph node and one Responses call, combining position teaching with played-move feedback. The old second node is disconnected. Position evidence is an independent top-five search; played moves reuse that evidence or receive a restricted root search when absent. Final positions use the same node without a played move. Engine analysis uses the FEN without prior repetition history.

For a locally running Windows Python backend, install the engine once:

```powershell
.\.venv\Scripts\python scripts\install_stockfish.py
```

The backend discovers the ignored `.tools/stockfish` installation automatically. Alternatively, set `STOCKFISH_PATH` to an existing engine executable. A standalone engine check works without an OpenAI key or a database:

```powershell
.\.venv\Scripts\python -m backend.coach.stockfish --fen "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1" --move e2e4
```

In Docker, use `docker compose exec app python -m backend.coach.stockfish` with the same `--fen` and `--move` arguments. This CLI loads `.env` for local engine settings.

### Position classification

The backend's standalone `backend.coach.position_classification.classify_position(fen)` and coaching analysis share five-move centipawn sharpness. Each evaluation is capped at ±2000 cp, including mates mapped by sign. Exponentially weighted adjacent gaps (λ=1) give raw D; `100 * min(1, log1p(D/10) / log1p(687.68/10))` gives a 0–100 score. Tags are Forgiving (≤20), Flexible (≤40), Selective (≤60), Demanding (≤80), and Critical (>80), without rounding before classification. Positions with fewer than five legal moves remain unclassified. Saved complete evidence is rescored locally on retrieval; old coaching prose is identified separately. See [usage, versioning, and edge cases](backend/coach/README.md#standalone-position-classification).

### Replay controls

- Click **Analyze** beside a saved game to open its dedicated replay screen, then use the replay buttons and slider.
- **Back to games** returns to the library with your filters, scroll position, and keyboard focus restored. Browser Back/Forward and replay links also work.
- Left/right arrows stop on the imported player's turns, briefly showing the intervening position for 100 ms. Black's first forward step advances only White's opening move. Backward navigation follows the same rule. Home/End keep the starting and final positions reachable even when the opponent is to move.
- The slider selects the same decision points; Space toggles autoplay through them. Reduced-motion preference skips the intermediate board. Shortcuts do not intercept form fields or the coach cards. Space retains its native action on focused buttons and links.
- Flip the board; the initial orientation follows the imported player.
- Selecting a game again restores your last settled position in this browser. Older bookmarks on an opponent's turn move back to the preceding player decision.
- The Coach response is one card containing the position thesis, candidate moves with instructional explanations, and feedback on your move. The decision classification is a colored heading tag. Evaluations are colored from the reviewed side’s perspective. The played move appears once within the same list, with a blue Player move badge and concise feedback; sound matching recommendations reuse their explanation. An optional link previews a stronger candidate. Select a candidate to draw its arrow and two instructional squares without playing it. Selection pauses autoplay; selecting the same candidate again, navigation, and new responses reset the overlay. Saved feedback restores automatically. Older reviews show their position teaching; rerun for combined move feedback.

## Coach backend

`backend/coach/` uses one LangGraph node and the OpenAI Responses API with GPT-6 Astra (default) or GPT-6.1 Terra, both with medium reasoning. The model dropdown remembers the selection. Both use the supplied combined prompt and strict JSON containing exactly thesis, candidates, and move evaluation. The node receives independent top-five Stockfish evidence and sharpness classification, plus separate played-move evidence. Expected-score loss of at most 5 percentage points is acceptable; larger losses are meaningfully inferior, and inconsistent evidence is uncertain. This candidate policy is separate from position sharpness and the player's move. Output validation checks legality, approved membership, highlights, and stronger-candidate references. The former second node never runs. Structured output and evidence persist as JSON; a one-time startup migration removes the retired needs field from saved structured reviews while preserving archived text and history; mistake-classification and sharpness versions are stored separately beside the output. The replay sends game ID, ply, and model; the server derives the trusted FEN and move. Position-only FEN requests remain supported. Unsupported models are rejected, and model changes apply to the next run. See [coach implementation details](backend/coach/README.md).

See [backend/coach/README.md](backend/coach/README.md) for the Python interface, command-line dry run, credentials, and Docker usage. Set `OPENAI_API_KEY` in the ignored project `.env`, then restart the app (`docker compose up -d` for Docker). The key is used only by the backend. The existing game library works without a key.

The same graph is available in LangSmith Studio through the root `langgraph.json`; Docker Compose starts its server automatically. See the coach README for Studio input, tracing setup, and optional local Python development. LangSmith tracing is optional: set `LANGSMITH_API_KEY`, `LANGSMITH_TRACING=true`, and `LANGSMITH_PROJECT=chess-coach` in `.env`, then run `docker compose up -d` to apply those settings to both services and record graph, node, and Responses API spans. App requests execute the graph directly and do not require the Studio server.

## Analyze a game

On a saved game's library row, **Analyze game** runs Stockfish for every recorded move made by the selected player, then automatically runs the coach for **inaccuracies, mistakes, and blunders**. Good and uncertain moves receive no automatic model call. Coaching uses the model selected in replay (GPT-6 Astra by default, with medium reasoning) and requires the configured OpenAI API key. Engine searches queue one at a time; coach generations are also serialized with manual Run coach requests. **Open game** remains available while analysis runs. Refreshing or navigating away does not stop the server job. Each engine result and successful coach response is saved immediately; **Resume analysis** continues unfinished work after a failure or app restart and reuses matching saved reviews.

Before coaching is saved, an analyzed decision displays the Moves section: the top three ranked engine moves (fewer if fewer are legal), plus the player's move if it is outside that three. A matching player move appears once. Each row shows its own score and the player's existing severity grade. Selecting a move previews its arrow and origin/destination on the board. Automatically saved teaching appears in replay as coaching progresses; manual Run coach remains available. Older completed engine-only games offer **Coach flagged moves**, which reuses their engine results and any existing matching coach feedback. New jobs also reuse the exact saved position and played-move evidence inside the existing single-node coach graph; older evidence without position context uses the normal coach search.

Markers under the replay slider flag the selected player's inaccuracies (amber), mistakes (orange), and blunders (red). Hover or keyboard focus identifies the move and grade; selecting a marker opens the position **before** that move. Good and uncertain moves have no error marker. The marker positions follow the player's replay stops, including Black-to-move starting positions.

`POST /api/games/{game_id}/analysis` takes `{"username":"player","model":"gpt-6-astra"}` (model optional) and returns a saved background job. `GET /api/games/{game_id}/analysis?username=player` returns progress and results without engine or model work. Summaries include `coach_total` and `coach_completed`; the job is completed only after eligible coaching is saved. The game-list API includes a compact `analysis` summary, and game detail includes `engine_analyses` keyed by player color plus saved `coach_responses`. The server derives positions and moves from the stored PGN and rejects players outside the game.

The additive `game_engine_analysis` table is created automatically at startup. Results are keyed by game, player color, and zero-based pre-move ply, and protected by a PGN fingerprint so a changed game cannot reuse stale results. The existing common-depth top-five position search and restricted played-root search supply the evaluations; the UI takes the first three ranked lines regardless of coaching candidate approval. Player severity reuses the existing logistic winning-chance loss and mate rules, with uncertain grades for unreliable comparisons. The single-worker requirement applies to analysis coordination as well as imports. Engine searches currently use individual FENs without prior repetition history, as in position coaching.

## Lessons

The **Lessons** tab shows the selected player's inaccuracies, mistakes, and blunders within each tactical and positional subcategory. Counts come from saved game analyses, with the latest matching coach review supplying the category. A move is counted once per game; repeated coach runs do not add errors, while the same decision played in another game counts as another occurrence. Good and uncertain moves are excluded. Errors without a supported current-version label remain in **Unclassified**; category-only labels are no longer emitted. The page states how many games and moves have been analyzed and provides player selection and refresh.

Choose the **Positional** or **Tactical** summary card to explore its errors, then filter by severity. Tactical exploration keeps **Missed tactics** and **Allowed tactics** separate by motif; positional topics use the piece in Stockfish’s best move. Topics are ordered by matching count, with bars showing their share of the current matching set. Expand a topic for its full severity breakdown. **Unclassified** remains separately accessible when present. Filtering uses saved counts without another request; the explorer shows aggregate counts rather than individual move lists.

Earlier review versions remain readable but count as Unclassified until refreshed. Use **Coach flagged moves** in the library or **Run coach** on an individual move; saved engine analysis is retained. Current reviews with an explicitly null classification remain Unclassified without being retried automatically.

`GET /api/lessons?username=player` is read-only. It excludes stale PGN results, mismatched positions, and opponent moves, and never starts Stockfish or OpenAI work. Only saved game-analysis decisions contribute; import and analyze a game to populate the breakdown.

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
