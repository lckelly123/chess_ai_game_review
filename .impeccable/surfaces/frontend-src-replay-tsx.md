---
version: 1
slug: "frontend-src-replay-tsx"
primary_target: "frontend/src/Replay.tsx"
related_targets: ["frontend/src/Board.tsx","frontend/src/GameOverview.tsx","frontend/src/MoveList.tsx","frontend/src/replayNavigation.ts","frontend/src/engineReview.ts","frontend/src/CoachCards.tsx","frontend/src/useCoachSpeech.tsx","frontend/src/styles.css"]
---

# Game replay

Mode: Operate. Route: `#game/{id}?player={username}`. Direction: `replay-moves-and-coach-navigation-2026-11-26`. Build path: code.

This is a user-approved extension of the existing dark study workspace. Preserve the pure-black palette, DM Sans outside Coach, Icy Sea board texture and Classic pieces. Coach uses Times New Roman, approved November 26, 2026. No generated comp or raster asset is introduced.

## Direction contract

- THESIS: Inspect every recorded half-move and move directly between saved coaching decisions.
- OWN-WORLD: Inherit flat dark surfaces, fine outlines, blue selection and focus, existing evaluation colors, and gently rounded panels.
- STORY: Select a recorded move, see it already played with origin/destination highlights, read its saved assessment, then follow green arrows through the selected player's coached errors.
- FIRST VIEWPORT: Move panel left of the board with exactly matching top and bottom edges; board and controls in the middle; Coach at right, with review arrows below the response. Narrow layouts move Coach below the board, then the move panel below the board controls.
- SIGNATURE INTERACTION: One navigation click plays one half-move and opens its saved review directly. The position explanation types out, followed by the played-move assessment. Previously read text appears immediately. No automatic exercise or default arrow interrupts replay.

## Data and behavior

Coach prose and move explanations use Times New Roman at 17px with 1.6 line height, 18px section headings, and a 20px panel title. Hint and structured explanation text reveal incrementally with short sentence pauses. Paragraphs reserve their final line wrapping; SAN and variation links appear as whole interactive units. Show all completes both queued explanation sections and preserves keyboard focus. Completed passages are remembered locally by response, section, and content so updated explanations still animate. Reduced-motion preferences show text immediately; screen readers receive complete text without character-by-character live announcements. Navigation cancels the previous passage's timers.

Normal navigation, error markers, and review jumps show the position after the selected move. The board highlights its origin and destination with the established last-move overlay; the default purple arrow is removed. The user approved going straight to the played position and saved review even for mistakes. Practice components and saved attempts remain in the codebase but replay does not invoke them. Move detail opens after the position narration completes.

Move numbers include Black-to-move starts. Scores use each mover's perspective; mate scores stay distinct and missing evidence stays unavailable. Last move and its evaluation refer to the selected move, while phase and sharpness describe the displayed position. The first position has no selected move; the final move retains its highlights and saved review. Stored engine and coach evidence remains keyed by the preceding decision ply. The reusable move list also selects the resulting position after SAN.

Replay buttons, keyboard arrows, slider and autoplay visit every half-move without paired transitions. Space can start autoplay after a direct review jump without hiding the revealed response. Opponent turns show the top three engine choices and their evaluations; the played move is fourth only when outside those three.

Green Previous review and Next review controls target only the selected player's inaccuracy, mistake or blunder with a matching saved response. Endpoints disable unavailable directions. New game analyses save both sides' engine evidence; lesson counts and automatic coaching remain selected-player-only. Older analyses offer Analyze remaining moves and reuse saved evidence and current reviews.

Move explanations embed short SAN PV excerpts in double brackets. Each complete excerpt is one inline link, matched against saved legal PV positions. Clicking autoplays the excerpt at one ply per second and holds its final position. A compact status below the board distinguishes variation playback and exposes Back to game and Replay throughout. Canonical game navigation stays unchanged during the demonstration; navigating or selecting another move cancels it. Full engine-continuation lists and the comparison button are removed. Explicit alternative selections show their instructional arrows and highlights on the pre-move decision position; selecting the played move keeps the board after it without an arrow. Unresolved excerpts stay readable as plain text.

## Quality bar and evidence

Played-position update: 85 frontend tests, production build, and 19 browser checks covering Qb4+ on b4 with b8/b4 highlights, flipped boards, direct saved reviews, explicit candidate arrows, saved variation playback and return, one-ply forward/back/keyboard/slider/autoplay, review jumps, error markers, reload, final positions, and 390px/320px layouts. Browser checks use synthetic games and make no API requests. Evidence: `.impeccable/review/played-move-browser-checks.json` and `played-move-*.png`. The detector only flags the unchanged Markdown quotation rule, an existing documented exception.

Coach flow validation: 71 frontend tests, production build, and 29 browser checks covering natural typing order, automatic success handoff, wrong attempts, skip/focus behavior, move/PV interactions, interrupted narration, revisits/reload, reduced motion, restored practice, and desktop/tablet/390px/320px layouts. Synthetic evidence is in `.impeccable/review/coach-browser-checks.json` and `coach-*.png`. The detector's sole finding is the existing neutral Markdown quotation rule documented in DESIGN.md.

Native keyboard controls, distinguishable selection/focus, meaningful missing/loading/error states, exact board/panel alignment on desktop, and no horizontal overflow at 320px or larger. Synthetic browser evidence: `.impeccable/review/replay-browser-checks.json` and replay desktop, laptop, tablet, mobile, small-mobile, and opponent screenshots. Five viewport captures and interaction checks passed; finish reviewer returned ship after the sole Space-key finding was resolved. Reported validation: 513 backend tests, 65 frontend tests, production build. No production game data or model calls were used for visual checks.
