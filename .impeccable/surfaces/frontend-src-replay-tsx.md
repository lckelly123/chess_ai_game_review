---
version: 1
slug: "frontend-src-replay-tsx"
primary_target: "frontend/src/Replay.tsx"
related_targets: ["frontend/src/MoveList.tsx","frontend/src/replayNavigation.ts","frontend/src/engineReview.ts","frontend/src/CoachCards.tsx","frontend/src/PracticeCard.tsx","frontend/src/useCoachSpeech.tsx","frontend/src/useReviewPractice.ts","frontend/src/styles.css"]
---

# Game replay

Mode: Operate. Route: `#game/{id}?player={username}`. Direction: `replay-moves-and-coach-navigation-2026-11-26`. Build path: code.

This is a user-approved extension of the existing dark study workspace. Preserve the pure-black palette, DM Sans outside Coach, Icy Sea board texture and Classic pieces. Coach uses Times New Roman, approved November 26, 2026. No generated comp or raster asset is introduced.

## Direction contract

- THESIS: Inspect every recorded half-move and move directly between saved coaching decisions.
- OWN-WORLD: Inherit flat dark surfaces, fine outlines, blue selection and focus, existing evaluation colors, and gently rounded panels.
- STORY: Read numbered White/Black SAN columns, select a pre-move position, inspect engine choices on either turn, then follow green arrows through the selected player's coached errors.
- FIRST VIEWPORT: Move panel left of the board with exactly matching top and bottom edges; board and controls in the middle; Coach at right, with review arrows below the response. Narrow layouts move Coach below the board, then the move panel below the board controls.
- SIGNATURE INTERACTION: Challenge, solve, then listen to the explanation. A correct practice move receives brief success feedback; the hint collapses and the position explanation types out, followed by the played-move assessment. Review arrows bypass practice for that visit. Previously read text appears immediately.

## Data and behavior

Coach prose and move explanations use Times New Roman at 17px with 1.6 line height, 18px section headings, and a 20px panel title. Hint and structured explanation text reveal incrementally with short sentence pauses. Paragraphs reserve their final line wrapping; SAN and variation links appear as whole interactive units. Show all completes both queued explanation sections and preserves keyboard focus. Completed passages are remembered locally by response, section, and content so updated explanations still animate. Reduced-motion preferences show text immediately; screen readers receive complete text without character-by-character live announcements. Navigation cancels the previous passage's timers.

Successful practice shows “Good move. Let’s look at why.” for 650ms, collapses the hint over 350ms, then expands the review over 320ms. Move detail opens after the position narration completes. Reduced motion keeps a brief 300ms success acknowledgment and skips spatial animation. Solved practice never restores the hint on revisit, and no View review click is required. Incorrect or failed attempts retain the hint and existing retry behavior.

White/Black columns use actual game move numbers, including Black-to-move starts. Scores use each mover's perspective; mate scores stay distinct and missing evidence stays unavailable. Clicking SAN opens the pre-move position. The current move remains visible within the internally scrolling list.

Replay buttons, keyboard arrows, slider and autoplay visit every half-move without paired transitions. Space can start autoplay after a direct review jump without hiding the revealed response. Opponent turns show the top three engine choices and their evaluations; the played move is fourth only when outside those three.

Green Previous review and Next review controls target only the selected player's inaccuracy, mistake or blunder with a matching saved response. Endpoints disable unavailable directions. New game analyses save both sides' engine evidence; lesson counts and automatic coaching remain selected-player-only. Older analyses offer Analyze remaining moves and reuse saved evidence and current reviews.

Move explanations embed short SAN PV excerpts in double brackets. Each complete excerpt is one inline link, matched against saved legal PV positions. Clicking autoplays the excerpt at one ply per second and holds its final position. A compact status below the board distinguishes variation playback and exposes Back to game and Replay throughout. Canonical game navigation stays unchanged during the demonstration; navigating or selecting another move cancels it. Full engine-continuation lists and the comparison button are removed. Position-explanation UCI links retain their existing selection behavior. Unresolved excerpts stay readable as plain text.

## Quality bar and evidence

Coach flow validation: 71 frontend tests, production build, and 29 browser checks covering natural typing order, automatic success handoff, wrong attempts, skip/focus behavior, move/PV interactions, interrupted narration, revisits/reload, reduced motion, restored practice, and desktop/tablet/390px/320px layouts. Synthetic evidence is in `.impeccable/review/coach-browser-checks.json` and `coach-*.png`. The detector's sole finding is the existing neutral Markdown quotation rule documented in DESIGN.md.

Native keyboard controls, distinguishable selection/focus, meaningful missing/loading/error states, exact board/panel alignment on desktop, and no horizontal overflow at 320px or larger. Synthetic browser evidence: `.impeccable/review/replay-browser-checks.json` and replay desktop, laptop, tablet, mobile, small-mobile, and opponent screenshots. Five viewport captures and interaction checks passed; finish reviewer returned ship after the sole Space-key finding was resolved. Reported validation: 513 backend tests, 65 frontend tests, production build. No production game data or model calls were used for visual checks.
