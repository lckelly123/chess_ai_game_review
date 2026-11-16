# AI Chess Tutor

<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
User-approved React/TypeScript frontend, Python/FastAPI backend, and PostgreSQL storage. Docker Compose runs the application and a PostgreSQL container with persistent storage. Successful coach feedback is saved by complete FEN and restored when revisiting a position.

## Users
Chess players reviewing their own completed games to understand positions and plans.

## Product Purpose
Import public Chess.com games, browse the library, and replay exact positions. Future coaching will teach position evaluation and planning. A standalone backend coach now supports explicit position requests through the OpenAI Responses API (GPT-6 Astra, xhigh). The replay screen can explicitly run the coach for its current position; student questions remain disconnected.

## Operating Context
Initial local, single-user application. Username-based import is public data access, not authenticated account linking. Chess.com is an external provider; availability and freshness are not guaranteed.

## Capabilities and Constraints
Recent standard-chess imports, a library-first opening screen with search and filters, and a separate game replay screen opened by Analyze. Returning to the library retains filters and list position. Replay includes position navigation and orientation controls. A Coach panel replaces the move list, with a read-only response area and an editable question draft saved per game; Run coach displays a response for the selected FEN while question drafts remain local. Original PGN and exact half-move indexes remain available for future coaching. No invented game data in the library. User approved proceeding directly in code.

## Brand Commitments
User selected a quiet light workspace with a blue-grey board and compact game list. On November 15, 2026, the user supplied a specific board reference and requested matching artwork: Icy Sea texture and Classic black-and-white pieces. The rest of the interface retains its existing identity; no implied affiliation with Chess.com.

## Product Principles
- Make the selected position and side to move unambiguous.
- Preserve source games and make repeated imports safe.
- Keep interactions responsive during external requests.
- Explain loading, empty, and failure states in plain language.

## Open Decisions
Public hosting, accounts, analysis workers, follow-up conversations remain future scope.
