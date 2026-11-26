# Game library and account

Mode: Operate. Route: `#games`, with account settings available throughout the app.
Primary target: `frontend/src/App.tsx`. Related targets: `frontend/src/AccountDialog.tsx`, `frontend/src/useGameLibrary.ts`, `frontend/src/styles.css`.

User-approved direction, November 25, 2026. Build path: code; extend the existing dark workspace.

- THESIS: Enter a Chess.com username once, then arrive directly at a current game library.
- OWN-WORLD: Preserve the pure-black canvas, DM Sans, fine borders, white actions, muted blue focus, existing board artwork and compact game rows.
- STORY: Set the account in the global header, browse saved games immediately, and let a background check add new completed games.
- FIRST VIEWPORT: Brand and navigation at left, one account button at top right; library title and quiet sync status, search and filters, then a taller game list. The former import panel and inline player selector are removed. On mobile, navigation sits below the brand/account row and sync status below the heading.
- SIGNATURE INTERACTION: Reload checks for new games while preserving the usable library. Sync completion retains filters and scroll; switching account ignores stale responses.
- QUALITY BAR: First-use prompt, native keyboard-accessible account dialog, remembered username, first 50 games, uncapped subsequent catch-up, deduplication, retryable failures, preserved saved games, and no horizontal overflow at 320px. Account selection is centralized across Library, Lessons and Multi-game analysis. Sync does not initiate engine or model analysis.

Implemented and reviewed November 25, 2026. Browser checks cover first setup, reload sync with usable saved games, preserved filters, failed-sync retry, account switching during a pending sync, and dialog focus/Escape behavior. Desktop, tablet, 390px and 320px layouts showed no horizontal overflow. Evidence: `.impeccable/review/browser-checks.json` and the desktop, mobile, account, empty, and sync-error screenshots in the same directory. Browser review uses synthetic games only in intercepted test responses; production has no demonstration data.
