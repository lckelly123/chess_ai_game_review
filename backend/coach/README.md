# Position and move coach

A standalone async LangGraph workflow using the OpenAI Responses API with `gpt-6-astra` (default, `reasoning.effort="medium"`) or `gpt-6.1-terra` (`reasoning.effort="medium"`). The replay screen calls it through `POST /api/coach/analyze` when Run coach is pressed. The Python interface, CLI, and LangSmith Studio use the same graph definition.

```mermaid
flowchart LR
    START --> analyze_position
    analyze_position -->|played move supplied| evaluate_move --> END
    analyze_position -->|no played move| END
```

Input is `fen` plus optional `played_move` in UCI. The board is always derived from that FEN. `analyze_position` returns structured position teaching; `evaluate_move` produces section 3 as Markdown. State retains separate `position_analysis`, `move_analysis`, and `stockfish` objects, plus readable combined `text` and total `usage`. Each pass retains its own model, response ID, and usage. The first pass also retains the validated JSON under `position_analysis.structured`. The top-level response ID/model identify the final completed pass. The normalized played move is available as `move_uci` in graph output and `played_move` in `CoachAnalysis` and HTTP responses.

## Flow

1. Receive the selected position's complete FEN.
2. Validate it with python-chess and generate a coordinate-labeled ASCII board. White is always at the bottom; letter case identifies piece color.
3. Send `system_prompt.md` as a system message, followed by a user message containing the FEN, ASCII board, and side to move. Require a strict Responses API `text.format` JSON schema. Validate the returned structure, legal candidate moves, and two distinct highlight squares per candidate before continuing.
4. If a played move exists, run Stockfish off the event loop to obtain up to eight root candidates plus the played move when outside the eight.
5. Send `move_prompt.md` as the second call's system message, with the first pass's validated JSON object, the same FEN/ASCII board, the played move in UCI/SAN, and engine evidence as user input. Both calls use the selected model with medium reasoning for both Astra and Terra, and `store=False`; prior output is sent explicitly rather than via a stored response ID. The second call has no JSON response format.
6. Append the second response to a readable Markdown rendering of the first pass for CLI/export compatibility. Without a played move, return only the first analysis. Invalid played moves are rejected before either model call; invalid generated teaching stops the graph before Stockfish, a second model call, or persistence.

An optional ASCII board can also be supplied. It must match the FEN, either as the coordinate-labeled output of `CoachPosition.from_fen(fen).ascii_board` or the plain eight rows from `str(chess.Board(fen))`. Whitespace differences are accepted. The canonical board is always sent to OpenAI, preventing mismatched or flipped inputs.

The first call receives no played move or engine information. The second receives only the reviewed move and supplied engine evidence, not the full PGN, result, or game history. Its generated Markdown is retained as returned.

## Structured position teaching

The first response contains exactly `position_character` (`quiet`, `tense`, or `forcing`), `positional_thesis`, `needs_of_position`, and `candidate_moves`. Each candidate contains `uci`, `reason`, and exactly two distinct `highlight_squares`. One to three distinct legal moves are required when moves exist; an empty array is accepted only when the side to move has no legal moves, including checkmate and stalemate. Word counts in the prompt are guidance rather than rejection rules. Position character describes the thinking required, not an engine evaluation.

Structured data is saved inside the existing `position_analysis` JSONB column without a migration. HTTP responses expose it as nullable `teaching`, alongside `candidate_san` labels derived by python-chess. These fields also survive feedback retrieval and game reload. The model does not generate SAN labels or arrow coordinates. The UI derives an arrow from UCI and uses the two supplied squares as instructional highlights; selecting a candidate pauses autoplay without playing the move. Navigation and new responses clear the selection, and flipping the board transforms the overlay. Old rows without structured data retain their original Markdown presentation. Rerun coaching to generate candidate annotations for an old position.

## Web endpoint

Both request modes accept optional `model`: `gpt-6-astra` (default) or `gpt-6.1-terra`. The endpoint validates this allowlist before starting work and passes a fresh `CoachSettings` to the existing coach factory. Its Responses adapter uses that model for both LangGraph nodes; there is no alternate API path or mutable global model. The same credentials, timeout, output budget, prompts, and engine settings apply. Model-access errors identify the requested model.

`POST /api/coach/analyze` accepts either `{ "game_id": "<saved game ID>", "ply": 0 }` for a recorded-move review, or `{ "fen": "<complete selected-position FEN>" }` for position-only coaching. `ply` counts half-moves already played; the next PGN move is reviewed. At the final recorded position, the game request runs only the first pass. Mixed modes and extra fields (including student questions) are rejected. The server derives the FEN/ASCII and played move and keeps prompts and credentials out of the browser. Only a complete successful run is saved; the response includes `fen`, nullable `played_move`, combined `text`, `model`, `response_id`, and `created_at`.

`GET /api/coach/feedback?fen=<URL-encoded FEN>&played_move=e2e4` returns the latest answer for that exact FEN plus move or `null`. Omitting the move selects position-only coaching. Game detail `coach_responses` are keyed by replay ply as a string; each selects the correct FEN/move pair, with legacy position-only feedback as a fallback. The table retains all successful generations and both passes' metadata and engine evidence. Schema upgrades add columns without deleting existing answers. Reruns append rows; failed second passes leave previous feedback untouched. Database failure returns 503 and never claims an unsaved answer was saved. Python/CLI/Studio calls remain independent of database storage.

The backend allows one active coach request per application process, returning 409 for overlapping requests. Invalid positions return 422, configuration/authentication problems 503, provider limits 429, timeouts 504, and other upstream failures 502. Provider error bodies are not exposed. Requests are not automatically retried.

The UI pauses autoplay when Run coach is pressed and shows progress. Moving to another position displays that position's saved answer; refreshing or reopening the replay restores it from PostgreSQL. The previous answer remains visible during a rerun and survives a failed generation. Student questions remain local drafts and are never sent. Leaving the replay aborts the browser request; it does not guarantee cancellation of a generation already running at OpenAI. A completed server request is still saved independently of the browser connection.

## Files

- `system_prompt.md`: the user's compact teaching prompt, with the authorized no-legal-moves exception.
- `move_prompt.md`: the move-review prompt, adapted to consume structured first-pass teaching.
- `teaching.py`: strict output schema, legal-move validation, SAN labels, and readable fallback rendering.
- `position.py`: FEN validation, ASCII rendering, and the position message.
- `settings.py`: supported models, default model, reasoning effort per model, and runtime limits.
- `graph.py`: input/state schemas, both nodes, conditional routing, and Studio export.
- `responses.py`: request construction, traced async SDK adapter, and response handling.
- `service.py`: compatible Python interface that invokes the graph.
- `routes.py`: position and move-review HTTP endpoint, concurrency guard, and safe error mapping.
- `__main__.py`: standalone command-line entry point and dry-run preview.

## Use from Python

Set `OPENAI_API_KEY` in the backend process environment, then call:

```python
from backend.coach import open_coach

async def analyze_selected_position(fen: str, played_move: str | None = None):
    async with open_coach() as coach:
        analysis = await coach.analyze(fen, played_move=played_move)
        return analysis.text
```

The context manager owns and closes the SDK client. It can be kept open for multiple calls. To integrate with a future application lifespan or a test transport, construct `Coach(existing_async_openai_client)` instead; the caller then owns the client.

For Terra, pass `CoachSettings.from_env(model="gpt-6.1-terra")` to `open_coach(settings)` or `Coach(existing_async_openai_client, settings)`. A settings instance belongs to that coach and applies to both passes. The CLI and standalone Studio graph continue to default to Astra. The UI remembers its selection in browser storage and disables it while a run is pending. Switching the selection does not fetch or generate another answer: the latest successful answer for the position/move remains visible with its actual model, and a subsequent successful run appends to the existing feedback history.

`coach.graph` exposes the compiled graph for streaming/debugging. `coach.analyze(fen, config={"tags": ["replay"], "metadata": {"game_id": "..."}})` accepts optional LangGraph run configuration; keep credentials out of metadata and graph state.

## LangSmith tracing

The Responses client uses LangSmith's `wrap_openai`. When tracing is enabled, a successful run has this hierarchy:

```text
chess_coach
  analyze_position
    OpenAI Responses (LLM request, output, token usage)
  evaluate_move (when a played move exists)
    OpenAI Responses (LLM request, output, token usage)
```

Graph/node failures and provider failures are captured at their respective levels. Set these values in the ignored project `.env` to send traces:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<your LangSmith API key>
LANGSMITH_PROJECT=chess-coach
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

Use your LangSmith region's endpoint if different. Set `LANGSMITH_WORKSPACE_ID` if your key is linked to multiple workspaces. Restart the backend or Studio server after changing these values. For Docker, run `docker compose up -d` after editing `.env`; Compose applies the same coach and tracing settings to both `app` and `studio`. Use `docker compose up --build -d` when code or dependencies have also changed. A plain container restart does not reread Compose's `.env` settings.

For an agent-based LangSmith workspace, first [connect the agent and retrieve its Local environment's `tracer_session_name`](https://docs.langchain.com/langsmith/create-an-agent#configure-integrations-that-require-a-project-name). Use that compatibility value for `LANGSMITH_PROJECT` instead of `chess-coach`.

The example configuration defaults to `LANGSMITH_TRACING=false`, so the coach and game library work without LangSmith credentials. With tracing enabled, prompts (including the selected position), answers, timing, errors, and usage are sent to LangSmith. OpenAI's `store=False` setting does not disable LangSmith trace storage.

## Run in LangSmith Studio

### Docker (default)

The ordinary app startup command also starts the local Agent Server:

```sh
docker compose up --build -d
```

`app` and `studio` run separate processes from the same image. That image includes the Studio CLI, runtime dependencies, `langgraph.json`, and Stockfish. Compose supplies credentials from `.env` at runtime; `.env` is excluded from the image. No local Python installation, `.venv`, or separate Studio command is needed. The Studio service starts independently of PostgreSQL and publishes only loopback port 2024 (configurable with `STUDIO_PORT`). It has its own `/ok` health check and saves development sessions under `/app/.langgraph_api` in the `studio-data` named volume. Ordinary restarts and `docker compose down` keep that data; `docker compose down -v` deletes it along with the app's named volumes.

Both services use the code built into the image. After source or dependency edits, rerun `docker compose up --build -d`. Inspect startup errors with `docker compose logs -f studio`. The container runs with browser auto-opening and source watching disabled; open the Studio link below in your host browser.

`langgraph.json` exports `backend.coach.graph:graph` as `chess_coach`. Graph loading and inspection require no OpenAI key; running a valid position requires `OPENAI_API_KEY`.

Open [Studio connected to the local server](https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024), select **chess_coach**, and submit:

```json
{
  "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  "played_move": "e2e4"
}
```

If `STUDIO_PORT` differs from 2024, change the port in the link's `baseUrl`. Use graph mode to inspect both nodes, inputs, outputs, and state. This workflow does not expose a chat/messages interface. A run with `played_move` makes two paid Responses calls; omit it for one position-only call. No automatic retries are made. Agent Server manages Studio threads/checkpoints. Each new invocation clears old move-review output; the optional move input is consumed for that invocation only, including when a prior run failed.

The existing FastAPI app executes the graph directly; it does not need this second server. Both entry points emit LangSmith traces when enabled, but app requests do not create Studio threads. Studio's server is a separate development surface and does not share FastAPI's single-request concurrency guard.

### Local Python (optional)

To develop with live source reloading outside Docker, stop the Docker Studio service first with `docker compose stop studio` to free port 2024, then run from the repository root on Windows:

```powershell
.\.venv\Scripts\python -m pip install -r backend\requirements-dev.txt
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\langgraph dev --host 127.0.0.1 --port 2024
```

The UTF-8 setting prevents the CLI's Unicode banner from failing in Windows terminals/pipes. This mode reads `.env` directly and stores development data in the ignored local `.langgraph_api/` directory. It uses a local Stockfish installation for the second node.

## Move review and engine evidence

The second node uses these engine helpers:

- `move_review.py`: `MoveReview.from_game(pgn, ply)` pairs the current replay position with the next recorded move, validates legality, derives ASCII/SAN, and provides a FEN-plus-UCI `review_key`. `from_fen(fen, played_move)` accepts a standalone pre-move position and UCI move. The final recorded position has no move to review.
- `stockfish.py`: `analyze_move(review)` runs local Stockfish and returns JSON-compatible evidence. It requests up to eight root candidates and performs an additional root-restricted search only if the played move is missing. All scores use the reviewed side's perspective; `score.cp` is in centipawns and `score.mate` in signed moves to mate (one is null). `score.bound` distinguishes exact search scores from lower/upper bounds. These are finite-depth engine estimates, not proofs of move quality. Each candidate includes UCI/SAN, legal principal variations, and actual depth. The two searches use the same depth/time caps but can reach different depths.
- `preparation_routes.py`: `POST /api/coach/prepare-move` with `{ "game_id": "...", "ply": 0 }` derives trusted inputs from the database's PGN, runs the engine off the event loop, and rejects concurrent engine work with 409. Missing games return 404; invalid positions or missing next moves 422; missing engine/configuration 503; engine deadlines 504; incomplete engine evidence 502. It makes no model calls and does not persist feedback.

Stockfish 19 is installed and checksum-verified during the Docker build. Local Windows development can run `python scripts/install_stockfish.py` from the repository root; the resulting `.tools/stockfish` directory is ignored by Git and Docker. An existing installation can instead be selected with `STOCKFISH_PATH`. Depth, seconds per search, threads, and hash MB default to 18, 10, 2, and 128 and are configurable in `.env.example`. Each analysis owns and closes its engine process. The engine receives the FEN only, without earlier repetition history. A local CLI preview is available through `python -m backend.coach.stockfish --fen "..." --move e2e4`; it loads `.env` and prints the complete preparation JSON without OpenAI or PostgreSQL.

The replay invokes the complete coaching graph; the separate preparation endpoint remains useful for inspecting engine inputs without a model call. The first-pass prompt and request remain position-only. The second node gets fresh engine evidence and only the current run's first response.

Keep clients/settings outside graph state and create any needed clients lazily. Do not hard-code a checkpointer in the exported graph: Studio supplies one, while direct application calls currently remain independent. A new FEN in a reused Studio thread generates a fresh board and does not send old analysis to OpenAI.

## Run without the UI

From the repository root, preview the first-pass request without credentials or network access:

```powershell
.\.venv\Scripts\python -m backend.coach --fen "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1" --dry-run
```

To make real, billable requests, set `OPENAI_API_KEY` in your local environment and omit `--dry-run`. Add `--move e2e4` to run the second pass, or omit it for position-only coaching. Add `--ascii-file path/to/board.txt` to validate an existing ASCII representation alongside the FEN. Dry runs validate the optional move but preview only the first request, without running Stockfish. The CLI prints the combined answer to stdout; errors go to stderr with a nonzero exit status.

Docker Compose passes `OPENAI_API_KEY`, `COACH_MAX_OUTPUT_TOKENS`, and `COACH_TIMEOUT_SECONDS` from the shell or the project's ignored `.env` file. After rebuilding the image, the same command can be run in a one-off container:

```powershell
docker compose run --rm --no-deps app python -m backend.coach --fen "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1" --dry-run
```

The FastAPI application loads the project `.env` at startup without overriding explicit process environment variables. The standalone CLI reads environment variables only; it does not automatically load `.env`. The game library starts normally without an OpenAI key.

## Limits and failures

- Output budget defaults to 32,768 tokens per model call, including internal reasoning and visible output. `COACH_MAX_OUTPUT_TOKENS` overrides it.
- Timeout defaults to 600 seconds per model call; `COACH_TIMEOUT_SECONDS` overrides it. A two-pass run can take longer than one call's timeout.
- Automatic retries are disabled to avoid another paid generation after an ambiguous timeout. The caller can explicitly retry.
- `store=False` requests that the response not be stored for later API retrieval. This is not a claim of zero data retention.
- Invalid FEN or mismatched ASCII raises `InvalidPositionError` before any API call.
- Missing credentials or invalid settings raises `CoachConfigurationError`.
- Incomplete, failed, refused, or empty responses raise `CoachResponseError`, with the response ID. Partial output is never presented as completed coaching.
- SDK connection, timeout, authentication, and quota errors propagate to Python callers; the CLI converts these to readable errors.

Tests use the real SDK with an in-memory HTTP transport. They do not call OpenAI or establish model access or chess-answer quality.

Graph tests additionally cover Studio import/schema, serialized output, client cleanup, repeated positions on a checkpointed thread, and nested success/error traces through a local LangSmith recorder. They do not establish live LangSmith ingestion.

## Official references

- [Stockfish 19 release and platform downloads](https://github.com/official-stockfish/Stockfish/releases/tag/sf_19)
- [python-chess engine analysis, MultiPV, and score perspectives](https://python-chess.readthedocs.io/en/latest/engine.html)
- [GPT-6 Astra and supported reasoning efforts](https://developers.openai.com/api/docs/models/gpt-6-astra)
- [Responses API request schema](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Reasoning model usage and token budgets](https://developers.openai.com/api/docs/guides/reasoning)
- [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangSmith OpenAI tracing](https://docs.langchain.com/langsmith/trace-openai)
- [Local Agent Server and Studio](https://docs.langchain.com/langsmith/local-dev-testing)
