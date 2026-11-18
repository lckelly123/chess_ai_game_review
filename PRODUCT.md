# AI Chess Tutor

<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
User-approved React/TypeScript frontend, Python/FastAPI backend, and PostgreSQL storage. Docker Compose runs the application with Stockfish and a PostgreSQL container with persistent storage. Successful move reviews are saved by complete FEN plus played move and restored when revisiting a position; older position-only feedback is preserved.

## Users
Chess players reviewing their own completed games to understand positions and plans.

## Product Purpose
Import public Chess.com games, browse the library, and replay exact positions. The coach teaches position evaluation and planning, then reviews the next recorded move against that plan and Stockfish evidence through two LangGraph nodes using the OpenAI Responses API (GPT-6 Astra with medium reasoning or GPT-6.1 Terra with medium reasoning). The Coach response is one box with two tabs: Position & plan groups the position character, concise thesis, needs, and selectable candidate moves; Evaluate your move contains the move review and colour-coded saved engine evaluations. Candidate selection illustrates one arrow and two important squares without advancing the board. Empty candidate lists are allowed when no legal moves exist. Older saved Markdown reviews retain their content within the same two tabs. Final positions receive position-only coaching; student questions remain disconnected.

## Operating Context
Initial local, single-user application. Username-based import is public data access, not authenticated account linking. Chess.com is an external provider; availability and freshness are not guaranteed.

## Capabilities and Constraints
Recent standard-chess imports, a library-first opening screen with search and filters, and a separate game replay screen opened by Analyze. Returning to the library retains filters and list position. Replay includes position navigation and orientation controls. A Coach panel replaces the move list, with a read-only response area and an editable question draft saved per game; Run coach displays a response for the selected FEN while question drafts remain local. Original PGN and exact half-move indexes remain available for future coaching. No invented game data in the library. User approved proceeding directly in code.

## Brand Commitments
User approved replacing the light workspace with a focused charcoal theme: near-black canvas, dark panels, soft white text and primary actions, muted blue selection, and DM Sans throughout. Retain the blue-grey board and compact game list. On November 15, 2026, the user supplied a specific board reference and requested matching artwork: Icy Sea texture and Classic black-and-white pieces. These assets remain unchanged; no implied affiliation with Chess.com.

## Product Principles
- Make the selected position and side to move unambiguous.
- Preserve source games and make repeated imports safe.
- Keep interactions responsive during external requests.
- Explain loading, empty, and failure states in plain language.

## Open Decisions
Public hosting, accounts, analysis workers, follow-up conversations remain future scope.
