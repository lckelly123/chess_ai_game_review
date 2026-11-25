# Third-party components

The replay board uses Chess.com's Classic piece set and Icy Sea board texture to match the reference image explicitly supplied by the user on November 15, 2026. These assets are bundled under `frontend/public/assets/chess/`; their exact source URLs are recorded in `SOURCES.json`. Artwork ownership remains with its respective rights holders; bundling does not grant a separate license or imply affiliation. The application icon and header knight remain original SVG geometry.

Dependencies retain their upstream licenses, available in their installed packages and source repositories:

- python-chess (`chess`): GPL-3.0-or-later, https://github.com/niklasf/python-chess. Its copyleft obligations need to be respected when distributing the application/container; no proprietary-license claim is made for this project.
- Lichess puzzler tagger: AGPL-3.0, https://github.com/ornicar/lichess-puzzler/tree/8e24b6d5e2b9618e41581a327926e4ac67c610a2/tagger. Source and licence are bundled in `backend/tactics/lichess`; adaptations are documented in `backend/tactics/README.md`.
- Stockfish 19: GPL-3.0, https://github.com/official-stockfish/Stockfish/tree/sf_19. The installer verifies the official release archive's SHA-256 and retains its license and source files alongside the executable (`/opt/stockfish` in Docker, `.tools/stockfish` locally). Corresponding release source: https://github.com/official-stockfish/Stockfish/releases/tag/sf_19.
- React: MIT, https://github.com/facebook/react.
- react-markdown: MIT, https://github.com/remarkjs/react-markdown.
- FastAPI: MIT, https://github.com/fastapi/fastapi.
- PostgreSQL: PostgreSQL License, https://www.postgresql.org/about/licence/.
- Psycopg 3: LGPL-3.0-or-later, https://www.psycopg.org/psycopg3/.
- Uvicorn: BSD-3-Clause, https://github.com/encode/uvicorn.
- HTTPX: BSD-3-Clause, https://github.com/encode/httpx.
- OpenAI Python SDK: Apache-2.0 (installed package metadata), https://github.com/openai/openai-python.
- Lucide: ISC, https://github.com/lucide-icons/lucide.
- DM Sans and Newsreader: SIL Open Font License 1.1, supplied through Fontsource. Font files are bundled locally; the running app does not contact a font CDN.

Chess.com API data remains subject to the provider's terms. Public lookup does not imply affiliation or a license to the provider's branding.
