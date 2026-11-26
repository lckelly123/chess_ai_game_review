# Dev

Mode: Operate. Route: `#dev`. Build path: code.
Primary target: `frontend/src/Dev.tsx`. Related targets: `frontend/src/dev.css`, `frontend/src/App.tsx`, `frontend/src/analysisReset.ts`, `backend/dev.py`.

User-requested extension of the existing workspace. Preserve the established visual world; no aesthetic selection, generated comp, or new raster assets.

## Direction contract

- THESIS: Make a fresh analysis run possible without losing the source game.
- OWN-WORLD: Inherit pure-black surfaces, DM Sans, fine rules, muted blue focus and selection, and the existing coral palette for destructive actions.
- STORY: Open Dev beside account settings, choose all saved games or search for one game, review the confirmation, then clear its derived analysis. Start any new analysis explicitly from the library.
- FIRST VIEWPORT: Reset analysis heading and Refresh, a separated Clear all analysis section, status feedback, then Clear one game with an All saved accounts label, search, and newest-first game rows. The current account does not limit this list.
- SIGNATURE INTERACTION: Both reset actions open a native dialog identifying the affected scope and preserved games. Cancel receives focus; Escape cancels; cancelling restores focus. Confirming disables conflicting controls and reports progress, success, or failure inline.
- RESPONSIVE: At 720px, bulk controls stack and row dates move below metadata. At 420px, row actions move to their own line and the account button hides its visible label. Keep Dev visible beside account settings and preserve usable controls at 375px and 320px.

## Data and interaction

Search matches player names or the local date across all saved accounts. Refresh reloads the saved-game list; load failures offer retry, an empty library explains account setup, and unmatched searches offer Clear search. All actions use real saved data.

Reset stops affected running work and clears engine results, game-owned coach feedback, browser practice attempts, and related multi-game reports. Per-game resets also invalidate report history for affected player libraries because coverage includes games without mistakes. Original games, PGNs, moves, and account associations stay intact. Shared legacy answers remain usable only by untouched games. Database analysis revisions and revision-aware practice keys prevent stale workers or browser attempts from restoring cleared state; reset events refresh open views. No reset starts new engine or coach work.

## Finish review

Disposition: **ship**. No material findings remain. Browser review exercised both resets against a disposable three-game database, search, confirmation and Escape, and verified that all three source games remained in the library. No console errors or horizontal overflow at 320px were observed. Desktop, 375px and 320px views and desktop/mobile confirmations are recorded in `.impeccable/review/desktop.jpg`, `mobile.jpg`, `mobile-320.jpg`, `confirmation.jpg`, and `mobile-confirmation.jpg`.

Validation: backend suite 539 passed; the final report-coverage regression was followed by 8 passing focused tests. Frontend 74 passed and the production build passed. These results and the browser checks are the implementation handoff evidence; this documentation pass preserves the existing token values and raster provenance.
