# Chess study

A local game library and replay workspace built with React, TypeScript, FastAPI, and PostgreSQL. Import completed standard-chess games from a public Chess.com username, search and filter your library, and replay positions on the board. Automatic coaching combines position teaching, candidate moves, and feedback on the next recorded move in one card using Stockfish evidence. One model response is generated and saved for future visits.

## Run with Docker

Start Docker Desktop with Linux containers. For a fresh checkout, copy `.env.example` to `.env` and set a nonempty `POSTGRES_PASSWORD`. Keep that password when reusing the database volume. Then from the repository root:

```sh
docker compose up --build -d
```

Open **http://localhost:8000**. Use **Account** in the top-right corner to enter your Chess.com username. The first sync adds up to 50 recent completed standard-chess games. Each subsequent page load or reload checks for new games automatically, while saved games remain available. Account settings also let you change username or switch to a saved account. No Chess.com password or API key is needed. The username is a public lookup, not verified ownership or account linking.

Automatic sync revalidates cached Chess.com responses using conditional requests. It catches up across all archive months since the newest saved game, revisits the preceding month for delayed publication when it overlaps the saved library's history, and deduplicates games without imposing the initial 50-game limit. Archive months before the oldest saved game are not requested, and older games are not backfilled. For a previously empty account, catch-up starts around its last successful check. Failed syncs preserve saved games; reloading the page starts another check. Chess.com's own publication/cache delay can still delay recently completed games. Syncing does not start engine or coach analysis.

The same command also starts the **Studio graph server** on http://127.0.0.1:2024. Open [LangSmith Studio](https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024) and select **chess_coach** to visualize and run the graph. The `app` and `studio` services use the same image, including Python, graph dependencies, and Stockfish; no local `.venv` or additional startup command is needed. Both services can also be started from the existing Compose stack in Docker Desktop after the first build. See [Studio inputs and tracing setup](backend/coach/README.md#run-in-langsmith-studio).

```sh
docker compose logs -f app
docker compose logs -f studio
docker compose down
```

Games and coach feedback are stored in PostgreSQL's `postgres-data` named volume and survive ordinary container recreation and `docker compose down`. **`docker compose down -v` deletes the named volumes.** PostgreSQL is reachable only on the Compose network by default. The opening screen is the game library. The frontend remembers the selected player and each game's replay position in the browser. This is a single-user local application: the app port binds to loopback by default, and there is no app authentication. Do not expose it publicly without adding access controls.

Set `PORT`, `STUDIO_PORT`, or a descriptive `CHESSCOM_USER_AGENT` in `.env` as needed. Both published ports bind to loopback; if you change `STUDIO_PORT`, use that port in Studio's `baseUrl`. The `db` service runs PostgreSQL 18; the app waits for its health check before starting. Studio starts independently of the app/database and keeps its development threads and checkpoints in the separate `studio-data` volume, which survives ordinary restarts and `docker compose down`. Rebuild with the usual command after code or dependency changes so both services use the same updated graph.

### Relational analytics storage

The first startup of this version replaces the retired JSON-based database tables and **discards existing application data**. This is the agreed clean cutover: there is no backfill and no SQLite import. The replacement is transactional and detects the old `games.id` layout; subsequent startups preserve the new data. Reimport games after upgrading.

`games` stores source facts and both players' accuracy. `game_moves` stores every half-move, its White-relative engine evidence, derived metrics, and one current coaching response. `review_attempts` stores ordered submissions for each independent practice session. Sync, HTTP caching, background jobs, standalone FEN coaching and multi-game reports use supporting tables. See [the storage contract](docs/storage.md) and [the complete schema](backend/schema.sql).

Game-linked coaching preserves the exact original JSON response plus queryable explanation, error and decision-context fields. `other` remains the raw category and is displayed as Positional. Decision context is Attack, Defend, Improve, Convert, or null. A successful rerun replaces the current move's response; a failed response never erases it. Standalone FEN and final-board commentary uses `coach_feedback` because it has no recorded move owner. Reading saved feedback makes no OpenAI call.

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

The preparation endpoint `POST /api/coach/prepare-move` accepts `{ "game_id": "<saved game ID>", "ply": 0 }`. API `ply` is the pre-move decision index: position 0 reviews White's first move, position 1 reviews Black's reply. Replay shows the position after its selected move, so a move selected at replay half-move N uses saved analysis from API ply N−1. The server derives the pre-move FEN, ASCII board, and next recorded move from the saved PGN. Passing the final position's index to preparation returns 422 because there is no next move, including games that ended by resignation or agreement; the final played move's review still uses the preceding index. Explore the endpoint at http://localhost:8000/docs.

It returns the validated move in UCI and SAN, a key derived from the complete FEN plus move, and Stockfish's top eight legal candidates (or fewer when fewer legal moves exist). The played move is evaluated separately from the same root position only when it is absent from the eight. Scores are from the side-to-move player's perspective, with centipawns and mate scores kept separate; principal variations and achieved search depths accompany the scores. The default search stops at depth 18 or 10 seconds per search, with two threads and 128 MB hash. Configure these limits through the `STOCKFISH_*` settings in `.env.example`.

The preparation endpoint makes no OpenAI calls and does not save feedback. The coach uses a single LangGraph node and one Responses call, combining position teaching with played-move feedback. The old second node is disconnected. Position evidence is an independent top-five search; played moves reuse that evidence or receive a restricted root search when absent. Final positions use the same node without a played move. Engine analysis uses the FEN without prior repetition history.

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

The backend's standalone `backend.coach.position_classification.classify_position(fen)` and coaching analysis share five-move centipawn sharpness. Each evaluation is capped at ±1000 cp (±10 pawns), including mates mapped by sign. Exponentially weighted adjacent gaps (λ=1) give raw D; `100 * min(1, log1p(D/10) / log1p(687.68/10))` gives a 0–100 score. Tags are Forgiving (≤20), Flexible (≤40), Selective (≤60), Demanding (≤80), and Critical (>80), without rounding before classification. Positions with fewer than five legal moves remain unclassified. Saved complete evidence is rescored locally on retrieval; old coaching prose is identified separately. See [usage, versioning, and edge cases](backend/coach/README.md#standalone-position-classification).

The independent Lichess **tactic classification** is disabled. Reviews do not run its motif detectors or additional Stockfish searches, and the UI does not display its findings from older saved reviews. Coach classifications and Lessons remain available. The detector source is retained; see [scope and provenance](backend/tactics/README.md).

### Replay controls

- Click **Analyze** beside a saved game to open its dedicated replay screen, then use the replay buttons and slider.
- **Back to games** returns to the library with your filters, scroll position, and keyboard focus restored. Browser Back/Forward and replay links also work.
- Left/right arrows advance or undo exactly one half-move, including opponent moves, with no intermediate state. Home/End keep the starting and final positions reachable for either player.
- The slider selects every half-move; Space toggles autoplay through them. Shortcuts do not intercept form fields or the coach cards. Space retains its native action on focused buttons and links.
- Flip the board; the initial orientation follows the imported player.
- Board changes play the bundled Lichess standard move or capture sound, including backward/forward navigation, autoplay, practice attempts, and engine-line playback. Initial loading, board flips, and annotation changes are silent. Audio becomes available after the first mouse, touch, or keyboard interaction.
- Selecting a game again restores your exact last position in this browser, including opponent moves.
- The Coach response is one card containing the position thesis, candidate moves with instructional explanations, and feedback on your move. The decision classification and 0–100 score appear in the left sidebar. Evaluations are colored from the reviewed side’s perspective. The played move appears once within the same list, with a blue Player move badge and concise feedback; sound matching recommendations reuse their explanation. An optional link previews a stronger candidate. Select a candidate to animate the current move back to the decision position, then play the chosen alternative. Selection pauses autoplay; selecting the same candidate again restores the recorded move. Navigation and new responses cancel the preview. Candidate arrows and square highlights are omitted. Saved feedback restores automatically. Older reviews show their position teaching; rerun for combined move feedback.

## Coach backend

`backend/coach/` uses one LangGraph node and the OpenAI Responses API with GPT-6 Astra (default) or GPT-6.1 Terra, both with medium reasoning. The replay displays saved coaching without model selection or manual generation controls. Both use the supplied combined prompt and strict JSON containing exactly thesis, candidates, and move evaluation. The node receives independent top-five Stockfish evidence and sharpness classification, plus separate played-move evidence. Expected-score loss of at most 5 percentage points is acceptable; larger losses are meaningfully inferior, and inconsistent evidence is uncertain. This candidate policy is separate from position sharpness and the player's move. Output validation checks legality, approved membership, and move references. Candidates contain only UCI and reasoning; saved highlight fields are ignored when reading older reviews. The former second node never runs. Structured output and evidence persist as JSON; the new storage retains the complete original model response; mistake-classification and sharpness versions are stored separately beside the output. The coaching API accepts game ID, ply, and model; the server derives the trusted FEN and move. Position-only FEN requests remain supported. Unsupported models are rejected, and model changes apply to the next run. See [coach implementation details](backend/coach/README.md).

See [backend/coach/README.md](backend/coach/README.md) for the Python interface, command-line dry run, credentials, and Docker usage. Set `OPENAI_API_KEY` in the ignored project `.env`, then restart the app (`docker compose up -d` for Docker). The key is used only by the backend. The existing game library works without a key.

The same graph is available in LangSmith Studio through the root `langgraph.json`; Docker Compose starts its server automatically. See the coach README for Studio input, tracing setup, and optional local Python development. LangSmith tracing is optional: set `LANGSMITH_API_KEY`, `LANGSMITH_TRACING=true`, and `LANGSMITH_PROJECT=chess-coach` in `.env`, then run `docker compose up -d` to apply those settings to both services and record graph, node, and Responses API spans. App requests execute the graph directly and do not require the Studio server.

## Analyze a game

On a saved game's library row, **Analyze game** runs Stockfish for every recorded move by both players, then automatically runs the coach for the selected player's **inaccuracies, mistakes, and blunders**. Good and uncertain moves and opponent moves receive no automatic model call. Coaching uses the previously saved model preference (GPT-6 Astra by default, with medium reasoning) and requires the configured OpenAI API key. Engine searches queue one at a time; coach generations are also serialized with direct coaching API requests. **Open game** remains available while analysis runs. Refreshing or navigating away does not stop the server job. Each engine result and successful coach response is saved immediately; **Resume analysis** continues unfinished work after a failure or app restart and reuses matching saved reviews. Both colors share canonical `game_moves` rows; the API groups them by the selected player so lesson counts and coaching progress keep their existing meaning. A later run for the other player reuses matching engine evidence. Older runs offer **Analyze remaining moves** in replay to fill opponent coverage while reusing existing player evaluations and current reviews.

Before coaching is saved, an analyzed decision displays the Moves section: the top three ranked engine moves (fewer if fewer are legal), plus the player's move if it is outside that three. A matching player move appears once. Each row shows its own score and the player's existing severity grade. Selecting an alternative animates the current move back, then plays that alternative using locally derived legal positions. Automatically saved teaching appears in replay as coaching progresses. The replay has no model selector or per-position coach-generation button. Games with complete engine coverage and pending coaching offer **Coach flagged moves**, which reuses their engine results and any existing matching coach feedback. New jobs also reuse the exact saved position and played-move evidence inside the existing single-node coach graph; older evidence without position context uses the normal coach search.

The replay's left sidebar contains a purple evaluation graph, a static White/Black summary (names, Lichess accuracy, and Good/Inaccuracy/Mistake/Blunder counts), and dynamic position information. It matches the board's height on desktop without an internal scrollbar and moves below the board on small screens. The graph, replay buttons, keyboard arrows, slider, and autoplay visit every half-move, including opponent turns. Opponent positions retain the engine candidate panel on the right.

The displayed board is normally **after the selected move**. An unsolved player error instead opens before the move for practice: selecting **…Qb4+** keeps Black's queen on b8, highlights b8 and b4 with borderless translucent red, and draws a small red arrow. The sidebar's position classification, existing 0–100 sharpness score, and phase describe the displayed position; Played, elapsed time, evaluation, and the saved review describe the selected recorded move. The starting position has no selected move; the final move remains reviewable. Every forward/back click selects exactly one half-move. Explicit engine or coaching alternatives undo the current move and animate the chosen move forward; game navigation cancels the preview. Timing uses PGN `[%emt]` when available, otherwise successive clocks for that player with the supported base/increment time control. Missing clocks, unknown time controls and custom-position starting clocks are not guessed.

The initial/intermediate timeline points are reconstructed from each move’s rank-one evaluation. The final-board evidence is saved on the last move in `engine_final_position`, including game-rule outcomes, mate winner, and search provenance. Whole-game accuracy is saved in `games.white_accuracy` and `games.black_accuracy` with a policy version. Both players’ accuracy follows the existing Lichess calculation; the final point retains repetition/50-move history for a recorded draw. Missing positions withhold accuracy. Results may differ from Lichess because the engine searches differ.

Phases follow the full Lichess Divider: middlegame begins with at most ten major/minor pieces, fewer than four own-colour pieces on either home rank, or mixedness above 150 using the 49 overlapping 2×2 regions. Endgame begins with at most six major/minor pieces, excluding kings and pawns. Transitions never reverse and can go directly from opening to endgame. Replay reconstructs phases from the PGN without extra engine work. No time graph is included.

Markers under the replay slider flag the selected player's inaccuracies (amber), mistakes (orange), and blunders (red). Hover or keyboard focus identifies the move and grade. Good and uncertain moves have no error marker. Green **Previous review** and **Next review** arrows beneath coaching jump only to the selected player's errors that already have saved coaching. Markers, review jumps and ordinary navigation open practice for unsolved errors, or the full review for completed exercises. Navigation and move numbering also support Black-to-move starting positions.

Practice displays the saved position hint and allows legal moves on the board. An accepted Good move stays visible briefly, animates back to the decision position, then the original recorded move animates forward. Each board change retains move/capture sounds, and the error squares stay red. Board input is disabled during grading and the handoff; autoplay pauses at unsolved errors, while manual navigation cancels pending checks and animations. Reduced motion preserves the sequence and sounds without piece movement. Only after the original move settles does **Understand the position** open, with the original move automatically active and its explanation queued after the position narration. Previously completed exercises open this review directly. Move lists show each move, badge and evaluation once, with selected explanatory text below. Explicit alternatives and saved variation excerpts remain available after practice. All coaching is generated in one response; clicking an explanation makes no new model or engine request.

Ordered attempts, technical grading failures, and the final Good move are saved in PostgreSQL in `review_attempts`. They survive navigation, refresh and browser changes. Each submission starts from the original decision position. Reopening resumes the latest session; **Practice again** creates the next review number. `GET /api/games/{game_id}/practice/{ply}` returns legal moves and saved sessions; `POST` grades and durably records a legal submission. `POST /api/games/{game_id}/practice/{ply}/reviews` starts/resumes a session, or starts a repeat with `repeat: true`. Submission IDs make network retries idempotent, and reset revisions reject stale writes. Practice never overwrites the original engine evidence or makes a model call.

`POST /api/games/{game_id}/analysis` takes `{"username":"player","model":"gpt-6-astra"}` (model optional) and returns a saved background job. `GET /api/games/{game_id}/analysis?username=player` returns progress and results without engine or model work. Summaries retain selected-player `total`, `completed`, and quality `counts`, add `opponent_total` and `opponent_completed`, and include `coach_total` and `coach_completed`. A null opponent total identifies older runs whose opponent coverage has not been checked. The job is completed only after both sides' engine results and eligible player coaching are saved. The game-list API includes a compact `analysis` summary, and game detail includes `engine_analyses` keyed by player color plus saved `coach_responses`. The server derives positions and moves from the stored PGN and rejects players outside the game.

All engine evidence now lives once per recorded move in `game_moves`; `analysis_jobs` holds only background progress and coaching ownership. Both player views reuse the same rows. Stored CP/mate scores use White’s perspective, including bound reversal for Black; API adapters supply the mover-relative evidence expected by grading and coaching. Raw PGN hashes and separate reset generations prevent stale writes. Analysis is resumable, and the single-API-worker requirement remains.

## Lessons

The **Lessons** tab shows the selected player's inaccuracies, mistakes, and blunders within each tactical and positional subcategory. Counts come from saved game analyses, with the latest matching coach review supplying the category. A move is counted once per game; repeated coach runs do not add errors, while the same decision played in another game counts as another occurrence. Good and uncertain moves are excluded. Errors without a supported current-version label remain in **Unclassified**; category-only labels are no longer emitted. The page states how many games and moves have been analyzed and provides player selection and refresh.

Choose the **Positional** or **Tactical** summary card to explore its errors, then filter by severity. Tactical exploration keeps **Missed tactics** and **Allowed tactics** separate by motif; positional topics use the piece in Stockfish’s best move. Topics are ordered by matching count, with bars showing their share of the current matching set. Expand a topic for its full severity breakdown. **Unclassified** remains separately accessible when present. Filtering uses saved counts without another request; the explorer shows aggregate counts rather than individual move lists.

Earlier review versions remain readable but count as Unclassified until refreshed. Use **Coach flagged moves** in the library when offered; individual refreshes remain available through the coaching API. Saved engine analysis is retained. Current reviews with an explicitly null classification remain Unclassified without being retried automatically.

`GET /api/lessons?username=player` is read-only. It excludes stale PGN results, mismatched positions, and opponent moves, and never starts Stockfish or OpenAI work. Only saved game-analysis decisions contribute; import and analyze a game to populate the breakdown.

Choose **Multi-game analysis** in Lessons to view previous cross-game coach responses for the selected player. **Run analysis** snapshots the current saved mistakes and makes one OpenAI Responses request with `gpt-6-astra` and `reasoning.effort="xhigh"`. Runs finish in the background, so leaving the page does not cancel them. Opening the screen, selecting an older response, refreshing, and polling never trigger a generation. A failed rerun preserves earlier responses. The model and effort are fixed for this workflow, independently of the replay coach selection.

The input starts with the same deterministic summary as Lessons, followed by every eligible error grouped into missed tactics, allowed tactics, positional, and unclassified. Each includes game/move context, the pre-move FEN and ASCII board, the opponent's previous move, the played evaluation and severity, available engine candidates and PVs (including the played-move continuation when saved), classification, and existing position/move explanations. Scores retain the player's perspective and distinguish centipawns from mate. Missing commentary stays missing; this workflow does not run Stockfish or generate individual move reviews. No mistakes are silently truncated if the input is too large.

The strict JSON report contains `profile_summary`, up to four `decision_patterns`, and up to three `foundation_priorities`. Patterns retain report-local IDs for foundation references but require no position IDs or supporting move IDs. Invalid, incomplete, empty, or refused answers are not saved as completed reports.

`POST /api/lessons/multi-game` accepts only `{"username":"player"}` and returns a saved background run with HTTP 202. `GET /api/lessons/multi-game?username=player` returns history, newest first. Duplicate active runs for a player are rejected; interrupted jobs require an explicit new run and paid requests are never automatically retried. The additive `multi_game_analysis` table stores the exact input snapshot, structured report, model, effort, usage, and timestamps. Existing `OPENAI_API_KEY`, `COACH_MAX_OUTPUT_TOKENS`, and `COACH_TIMEOUT_SECONDS` settings apply. Use one API worker, as with game analysis.

LangGraph Studio exposes **multi_game_coach** separately from **chess_coach**. Its only path is `START → analyze_patterns → END`, with no nodes or edges connecting it to the position coach. Studio takes the same `summary` and `mistakes_by_category` input; the app supplies these from saved data.

## Dev: reset analysis

The **Dev** tab beside the account control opens a searchable list of every saved game across all accounts. **Clear analysis** resets one game; **Clear all** resets every game, independently of the search filter. Both actions ask for confirmation. They preserve game records, original PGNs and played moves, metadata, saved accounts, and import caches. No analysis starts automatically after a reset.

Resets remove both players' engine results, coach feedback, analysis progress, and related multi-game reports. Reports for affected player libraries are invalidated because their coverage summaries also depend on the cleared game. Lessons is recomputed from the remaining saved analysis. Game-linked reviews belong to a specific move. Standalone FEN responses do not attach themselves to imported games.

Practice attempts and completion are server-backed and cleared in the same transaction as analysis. Coach narration progress and replay bookmarks remain browser preferences; reset notifications clear those locally. A durable per-game reset revision also prevents old clients from submitting stale practice or analysis results. Account and model preferences are retained.

`GET /api/dev/games` lists saved games. `POST /api/dev/analysis/reset` takes `{"game_id":"..."}` for one game or `{}` for all games. It cancels affected background jobs and deletes derived records in one database transaction. Reset revisions guard against late engine or coach writes restoring old results, including after a fresh run starts. These controls follow the application's existing local, single-user, single-API-worker model.

## Import behavior

The backend reads the documented [Chess.com Published Data API](https://www.chess.com/news/view/published-data-api). Imports run in the background, one at a time, with progress polling. They inspect up to the latest 24 available archive months, newest first, stopping at the requested number of valid standard-chess games. Variants, unfinished games, and malformed PGNs are skipped and reported. Each import adds to the library and deduplicates using the source game URL; requesting the latest 100 expands the same recent window, not an older-history pagination cursor.

Requests are serial, cached for 15 minutes locally, and conditionally revalidated using ETag/Last-Modified. Rate limits and temporary errors receive bounded retries. Chess.com's own cache can delay new games longer. Imports are committed atomically; a failed import preserves the existing library. In-progress job status is held in memory and expires on server restart; repeating an interrupted import is safe. Run a single API worker for this local version so import coordination and progress stay in one process.

PostgreSQL stores original PGNs and provider payloads alongside normalized game and move columns. Ingestion replays every half-move once, including castling, en passant, promotion and custom starting positions, to save board features and timing. Game detail reads those stored move rows. Engine work and coaching run only when requested, independently of import.

## Checks

```powershell
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f compose.test.yaml down
cd frontend
npm run build
```

The test stack uses a separate PostgreSQL container with temporary storage and no production credentials or OpenAI calls. Tests cover the one-time replacement, all four phases, raw coaching output, White-relative CP/mate/bound round trips, real Stockfish persistence, idempotent imports and submissions, repeat sessions, restarts, and stale-worker rejection. For local pytest, set `TEST_DATABASE_URL` to a disposable PostgreSQL database; each test uses an isolated schema. `npm run build` checks TypeScript before bundling. Dependencies are pinned in the existing lockfiles.

## Project layout

- `backend/main.py`: API, import jobs, lifecycle, and static frontend serving.
- `backend/importer.py`: Chess.com client, caching, retries, and bounded imports.
- `backend/database.py` and `backend/schema.sql`: PostgreSQL persistence and tables.
- `backend/ingestion.py` and `backend/analysis_storage.py`: phase-specific source parsing and engine serialization.
- `backend/chess_games.py`: source normalization and PGN replay.
- `frontend/src/`: library, board, replay, and styles.
- `backend/coach/`: extensible LangGraph coach, traced Responses adapter, prompt, validation, and CLI.
- `langgraph.json`: local Agent Server/Studio graph registration and environment configuration.

This project is independent of Chess.com. See `THIRD_PARTY_NOTICES.md` for dependency licensing. The future AI product needs a separate review of Chess.com's API guidance and AI-use terms; game analysis and explicit service/CLI requests send selected positions and, when available, played moves and engine evidence to OpenAI; student questions are not sent.
