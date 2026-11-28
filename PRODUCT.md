# AI Chess Tutor

<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
User-approved React/TypeScript frontend, Python/FastAPI backend, and PostgreSQL storage. Docker Compose runs the application with Stockfish and a PostgreSQL container with persistent storage. Successful move reviews are saved by complete FEN plus played move and restored when revisiting a position; older position-only feedback is preserved.

## Users
Chess players reviewing their own completed games to understand positions and plans.

## Product Purpose
Save a public Chess.com username once, keep its completed games in sync, browse the library, and replay exact positions. The coach teaches position evaluation and planning, then reviews the next recorded move against that plan and Stockfish evidence through two LangGraph nodes using the OpenAI Responses API (GPT-6 Astra with medium reasoning or GPT-6.1 Terra with medium reasoning). The Coach response is one box with two tabs: Position & plan groups the position character, concise thesis, needs, and selectable candidate moves; Evaluate your move contains the move review and colour-coded saved engine evaluations. Candidate selection animates the current move back to its decision position, then plays the selected alternative without arrows or instructional square highlights. Empty candidate lists are allowed when no legal moves exist. Older saved Markdown reviews retain their content within the same two tabs. Final positions receive position-only coaching; student questions remain disconnected.

## Operating Context
Initial local, single-user application. Account settings store a public Chess.com username for game syncing, not authenticated account linking; no password is required. Chess.com is an external provider; availability and freshness are not guaranteed.

## Capabilities and Constraints
The persistent header links Your game library and Analytics and provides one account dialog for adding or changing the remembered Chess.com username and selecting saved accounts throughout the app. Each app load or reload checks for completed standard-chess games while saved games remain usable. A first sync imports up to 50 recent games; subsequent checks catch up on new games without a count cap and deduplicate existing records. Sync completion preserves library filters and scroll; failures retain saved games and offer retry. Sync starts no engine or model analysis. The library-first opening screen has search and filters, with a separate game replay screen opened by Analyze. Returning to the library retains filters and list position. Replay includes position navigation and orientation controls. A Coach panel replaces the move list, with a read-only response area and an editable question draft saved per game; Run coach displays a response for the selected FEN while question drafts remain local. Original PGN and exact half-move indexes remain available for future coaching. No invented game data in the library. User approved proceeding directly in code.

Analytics replaces Lessons at `#analytics`; old `#lessons` and `#lessons/multi-game` bookmarks resolve there while saved coaching and multi-game reports remain intact. Seven graphs show missed and allowed tactical motifs, positional decision contexts, actual versus engine-preferred pieces, decision context by position outlook, and error rates by game phase, sharpness, and outlook. Speed and exact time-control filters use seven persisted summaries per player and time control, summing counts before calculating rates. Tactical and positional graphs require saved coach classifications; rates use reliably graded player moves, with inaccuracies, mistakes, and blunders counted as errors and uncertain grades excluded. Outlook is player-relative and measured before the move. Text descriptions, numeric heatmap cells, and expandable data tables expose the values and rate samples. Empty samples remain distinct from zero errors. Page load, manual refresh, imports, saved analysis/coaching, and resets update summaries without starting engine or model work; the visible page also reads saved updates every ten seconds. The page explains loading, account selection, missing analysis, and retry states; refresh failures retain the last loaded summary.

The Dev link beside account settings opens `#dev`, where players can search all saved games across accounts and explicitly clear one game's analysis or clear all. Confirmation names the scope and preserves original games, PGNs, moves, and account associations. A reset stops affected work and removes engine results, coach reviews, practice attempts, and related multi-game report history, including reports for affected player libraries whose coverage counts would be stale. New feedback belongs to its game; shared legacy answers remain available only to untouched games. Database revisions and browser practice keys prevent old results or attempts from reappearing. Resetting never starts fresh analysis automatically.

## Brand Commitments
User approved replacing the light workspace with a focused charcoal theme: near-black canvas, dark panels, soft white text and primary actions, muted blue selection, and DM Sans for the working interface. On November 26, 2026, the user approved Times New Roman in Coach, incremental text narration, and an automatic animated handoff from the solved challenge to position and move explanations. Retain the blue-grey board and compact game list. On November 15, 2026, the user supplied a specific board reference and requested matching artwork: Icy Sea texture and Classic black-and-white pieces. These assets remain unchanged; no implied affiliation with Chess.com.

## Product Principles
- Replay advances one recorded half-move at a time. An unsolved player error opens before the move, with red origin/destination squares, a small red arrow and a practice hint. An accepted better move is undone, then the original move is played with sound before its saved review opens. Completed exercises restore the played position and expanded assessment directly.
- Make the selected position and side to move unambiguous.
- Preserve source games and make repeated imports safe.
- Keep interactions responsive during external requests.
- Explain loading, empty, and failure states in plain language.

## Open Decisions
Public hosting, authenticated user accounts, analysis workers, follow-up conversations remain future scope.
