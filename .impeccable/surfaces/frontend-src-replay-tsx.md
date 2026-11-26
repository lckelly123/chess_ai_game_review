---
version: 1
slug: "frontend-src-replay-tsx"
primary_target: "frontend/src/Replay.tsx"
related_targets: ["frontend/src/MoveList.tsx","frontend/src/replayNavigation.ts","frontend/src/engineReview.ts","frontend/src/CoachCards.tsx","frontend/src/styles.css"]
---

# Game replay

Mode: Operate. Route: `#game/{id}?player={username}`. Direction: `replay-moves-and-coach-navigation-2026-11-26`. Build path: code.

This is a user-approved extension of the existing dark study workspace. Preserve the pure-black palette, DM Sans, Icy Sea board texture and Classic pieces. No new visual identity, generated comp, or raster asset is introduced.

## Direction contract

- THESIS: Inspect every recorded half-move and move directly between saved coaching decisions.
- OWN-WORLD: Inherit flat dark surfaces, fine outlines, blue selection and focus, existing evaluation colors, and gently rounded panels.
- STORY: Read numbered White/Black SAN columns, select a pre-move position, inspect engine choices on either turn, then follow green arrows through the selected player's coached errors.
- FIRST VIEWPORT: Move panel left of the board with exactly matching top and bottom edges; board and controls in the middle; Coach at right, with review arrows below the response. Narrow layouts move Coach below the board, then the move panel below the board controls.
- SIGNATURE INTERACTION: A review-arrow jump reveals matching saved coaching and the played-move assessment immediately, bypassing practice for that visit. Ordinary move navigation retains the existing practice flow.

## Data and behavior

White/Black columns use actual game move numbers, including Black-to-move starts. Scores use each mover's perspective; mate scores stay distinct and missing evidence stays unavailable. Clicking SAN opens the pre-move position. The current move remains visible within the internally scrolling list.

Replay buttons, keyboard arrows, slider and autoplay visit every half-move without paired transitions. Space can start autoplay after a direct review jump without hiding the revealed response. Opponent turns show the top three engine choices and their evaluations; the played move is fourth only when outside those three.

Green Previous review and Next review controls target only the selected player's inaccuracy, mistake or blunder with a matching saved response. Endpoints disable unavailable directions. New game analyses save both sides' engine evidence; lesson counts and automatic coaching remain selected-player-only. Older analyses offer Analyze remaining moves and reuse saved evidence and current reviews.

Move explanations embed short SAN PV excerpts in double brackets. Each complete excerpt is one inline link, matched against saved legal PV positions. Clicking autoplays the excerpt at one ply per second and holds its final position. A compact status below the board distinguishes variation playback and exposes Back to game and Replay throughout. Canonical game navigation stays unchanged during the demonstration; navigating or selecting another move cancels it. Full engine-continuation lists and the comparison button are removed. Position-explanation UCI links retain their existing selection behavior. Unresolved excerpts stay readable as plain text.

## Quality bar and evidence

Native keyboard controls, distinguishable selection/focus, meaningful missing/loading/error states, exact board/panel alignment on desktop, and no horizontal overflow at 320px or larger. Synthetic browser evidence: `.impeccable/review/replay-browser-checks.json` and replay desktop, laptop, tablet, mobile, small-mobile, and opponent screenshots. Five viewport captures and interaction checks passed; finish reviewer returned ship after the sole Space-key finding was resolved. Reported validation: 513 backend tests, 65 frontend tests, production build. No production game data or model calls were used for visual checks.
