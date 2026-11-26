---
name: Chess study
description: A focused pure-black workspace for revisiting your games, one position at a time.
colors:
  primary: "#f1f2f4"
  primary-hover: "#d9dce1"
  focus: "#91b4d3"
  workspace: "#000000"
  surface: "#000000"
  ink: "#f1f2f4"
  muted: "#a5adb8"
  line: "#2b2e34"
  field-border: "#606773"
  selected-row: "#1d2b38"
  hover: "#202329"
  accent: "#91b4d3"
  accent-hover: "#c3daed"
  primary-ink: "#16181c"
  body: "#d6d9df"
  selection-badge: "#2b4257"
  warning-surface: "#342d20"
  warning-ink: "#e6c389"
  severity-mistake: "#efaa72"
  board-light: "#d6e4e9"
  board-dark: "#7399ad"
  last-move-overlay: "#d4d57088"
  original-move-arrow: "#9565df"
  replay-accent: "#b69af5"
  replay-selected: "#271e3b"
  check: "#d3978cb0"
  win-surface: "#1d3328"
  win-ink: "#9bd5b0"
  loss-surface: "#392622"
  loss-ink: "#f0ad9f"
  draw-surface: "#202329"
  draw-ink: "#a5adb8"
  error-surface: "#392622"
  error-ink: "#f0ad9f"
typography:
  display:
    fontFamily: "'DM Sans Variable', sans-serif"
    fontSize: "38px"
    fontWeight: 550
    lineHeight: 1.15
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "'DM Sans Variable', sans-serif"
    fontSize: "19px"
    fontWeight: 600
    letterSpacing: "-0.02em"
  game-title:
    fontFamily: "'DM Sans Variable', sans-serif"
    fontSize: "24px"
    fontWeight: 600
    letterSpacing: "-0.03em"
  title:
    fontFamily: "'DM Sans Variable', sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-0.015em"
  body:
    fontFamily: "'DM Sans Variable', sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.65
  coach-body:
    fontFamily: "'Times New Roman', Times, serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.6
  working:
    fontFamily: "'DM Sans Variable', sans-serif"
    fontSize: "13px"
    fontWeight: 400
  label:
    fontFamily: "'DM Sans Variable', sans-serif"
    fontSize: "12px"
    fontWeight: 600
  caption:
    fontFamily: "'DM Sans Variable', sans-serif"
    fontSize: "11px"
    fontWeight: 400
  lesson-heading:
    fontFamily: "'DM Sans Variable', sans-serif"
    fontSize: "20px"
    fontWeight: 600
    letterSpacing: "-0.02em"
  lesson-total:
    fontFamily: "'DM Sans Variable', sans-serif"
    fontSize: "36px"
    fontWeight: 550
    lineHeight: 1
    letterSpacing: "-0.03em"
rounded:
  board: "0px"
  move: "4px"
  control: "8px"
  field: "8px"
  panel: "12px"
spacing:
  tight: "4px"
  inline: "8px"
  compact: "12px"
  standard: "16px"
  inset: "20px"
  workspace: "24px"
  replay-gap: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-ink}"
    rounded: "{rounded.field}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "9px 16px"
  button-danger:
    backgroundColor: "{colors.error-surface}"
    textColor: "{colors.error-ink}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-danger-hover:
    backgroundColor: "{colors.error-ink}"
    textColor: "{colors.error-surface}"
  button-text:
    textColor: "{colors.accent}"
    typography: "{typography.label}"
    padding: "0px"
  button-icon:
    rounded: "{rounded.control}"
    width: "36px"
    height: "36px"
  button-play:
    backgroundColor: "{colors.hover}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    width: "38px"
    height: "36px"
  input-username:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    height: "46px"
    padding: "10px 12px"
  account-button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  game-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    padding: "14px 20px"
  coach-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.body}"
    typography: "{typography.coach-body}"
    rounded: "{rounded.panel}"
    padding: "16px"
  candidate-selected:
    backgroundColor: "{colors.selected-row}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "12px 8px"
  result-win:
    backgroundColor: "{colors.win-surface}"
    textColor: "{colors.win-ink}"
    rounded: "{rounded.move}"
    padding: "6px 10px"
  board:
    rounded: "{rounded.board}"
  replay-game-overview:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
    width: "280px"
  coach-review-navigation:
    textColor: "{colors.win-ink}"
    rounded: "{rounded.control}"
    height: "44px"
    padding: "6px"
  navigation-tab:
    textColor: "{colors.muted}"
    padding: "0px 2px"
  navigation-tab-current:
    textColor: "{colors.ink}"
  lessons-overview-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "22px 24px"
  lessons-filter:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  lessons-tactic-filter-selected:
    backgroundColor: "{colors.selected-row}"
    textColor: "{colors.accent-hover}"
  lessons-severity-filter-selected:
    backgroundColor: "{colors.hover}"
    textColor: "{colors.ink}"
  lessons-topic:
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "18px 16px"
---

# Design System: Chess study

## Overview

**Creative North Star: "A focused study desk"**

A focused pure-black workspace gives the chess position a clear visual anchor while providing comfortable room for coaching. Blue-grey squares, soft white text, and a compact library support patient review. DM Sans carries headings and the working interface.

This records the implemented account, library, Lessons, Dev, and replay UI and the user's approved replacement of the light workspace with a dark theme. Pure-black canvas and panels, blue selection, and white primary actions define the surrounding interface. The board artwork follows the user's November 15, 2026 reference and retains its established texture and pieces.

**Key Characteristics:**
- Dark, flat surfaces separated by fine rules and tonal changes.
- An Icy Sea textured board with Classic black-and-white pieces, matching the supplied reference.
- Compact game rows and precise move selection.
- DM Sans for the working interface; Times New Roman for the Coach panel.

## Colors

The palette is cool and muted, with semantic colors reserved for game and request state. Frontmatter contains the normative values; the sidecar's generated tonal ramps are preview metadata, not additional implementation tokens.

### Primary

Soft white identifies primary actions such as Add account and Save account, with charcoal labels and a slightly darker hover state. Muted sky blue identifies text actions, keyboard focus, and selected move outlines. Replay play/pause uses a neutral tonal fill.

### Neutral

The workspace, panels, and fields share a pure jet-black (#000000) background. Soft white carries headings and controls, lighter grey carries coaching prose, and muted grey carries supporting text. Subtle rules divide sections; brighter field borders define interactive controls. Dark blue fills identify selections and the Analyze hover state. The header shares the workspace canvas.

### Semantic and board colors

The locally bundled Icy Sea image supplies the board's textured light and blue squares; board color tokens are fallback colors. Translucent olive marks the last move and muted coral marks check, preserving the texture beneath each highlight. Wins use light sage on dark green, losses and errors use light coral on dark clay, and draws use muted grey on a neutral fill, always accompanied by text. Amber on dark ochre marks a clear decision preference.

**The Position State Rule.** Keep last-move squares and check distinguishable, and announce the settled side to move or final position to screen readers.

Lessons segmented bars and severity dots use warning amber for Inaccuracy, warm orange for Mistake, and the existing negative coral for Blunder. Text summaries, named breakdowns, and a legend explain every severity color; counts remain neutral. Sky blue identifies the selected overview card and proportional topic bars. These severity roles match the library counts; the replay timeline retains its distinct stronger red Blunder marker.

Dev reuses light coral on dark clay for destructive actions, with a coral outline and inverted hover colors. The written action and confirmation explain the consequence; color alone never carries it.

## Typography

Locally bundled DM Sans Variable supplies headings, controls, names, metadata, and notation outside Coach. The Coach panel uses Times New Roman with Times and serif fallbacks. The game-title separator uses DM Sans at regular weight. Newsreader is no longer imported.

The library title is (38px), opponent names (14px), and working controls (12-14px). The account dialog uses a (22px) heading, a (16px) username field, and (12-13px) supporting text. At narrow widths the library title becomes (32px) and game titles (23px). Below (370px), the library title becomes (29px). Coach prose uses Times New Roman (17px) text at (1.6) line height with a maximum line length of (72ch); section headings use (18px) and the Coach title (20px). Candidate explanations use (17px), move-list SAN (14px), and score chips (12px). Counts, dates, and evaluations use tabular numerals where applicable.

Lessons reuses the display title, with its own heading and total roles from the frontmatter. Topic labels use (16px) at (550) weight, while supporting descriptions and matching counts use (13px). Overview totals and all breakdown counts use tabular numerals. Mobile size changes are recorded in Layout.

Multi-game analysis uses the same DM Sans hierarchy. Report prose is (16px) with a (1.75) line height and a maximum line length of (75ch). Section headings use (21px), pattern and practice titles (17px), and thinking-adjustment labels (13px) in the existing light blue accent. Confidence and saved-sample metadata use muted (12px) text.

## Layout

The app has library, replay, Lessons, Multi-game analysis, and Dev screens. The root URL opens the game library without a board. The library is centered at a maximum outer width of (1120px), with (38px 36px 24px) padding. A (68px) canvas-colored header holds brand and navigation at left and the Dev link beside a compact account button at right. The title and quiet sync status lead directly into search, filters, and a scrollable list. Desktop rows align result, opponent, time control, date, and analysis actions in columns; the list height is capped by the larger of (320px) and the dynamic viewport height minus (350px). Account entry and saved-account selection live in the global dialog.

Lessons shares the library container. Its title sits opposite the Multi-game analysis link and refresh control with a (24px) gap and (28px) space before the content. The global header supplies account selection. A compact error count and library-coverage summary precede two equal-width Positional and Tactical overview buttons with an (18px) separation and a (16px) grid gap. A separate Unclassified row appears below when needed. A fine rule introduces the explorer, with (20px) outer separation and (28px) top padding. Tactical subgroup controls form two equal columns; severity filters form four. Topic disclosures occupy the full width beneath them. Coverage notes follow after (28px), separated by a rule and (18px) top padding.

The Lessons heading includes a secondary Multi-game analysis link to `#lessons/multi-game`. This screen shares the library container and places Back to lessons above the title and primary Run analysis action. A refresh control and wrapping saved-sample counts sit above a fine rule; account selection remains in the global header. Coach responses begins after (32px), with a labeled saved-response selector opposite its heading. The report follows as unboxed prose; major sections have (36px) separation, (28px) top padding, and a fine divider.

Analyze opens a hash route containing the game ID and player. The dedicated replay screen has a maximum outer width of (1660px), with three tracks: a (280px) move panel, the board capped at (840px), and a (400px) Coach sidebar, separated by (32px) gaps. The outlined move panel aligns exactly with the board's top and bottom edges and scrolls internally. The board scales to the remaining width. The game heading and Back to games link follow the board's left edge. Inside Coach, one outlined response panel spans the available width, followed by green review-navigation arrows. Position teaching, the original move control, and selected move detail share one card; the existing exercise card precedes it when practice is available. The Coach panel grows with its content and the page scrolls naturally. Browser navigation and direct replay links work. Returning within the session restores filters, list/page scrolling, and focus to the originating Analyze link. Replay position remains saved per game.

- At (1300px) and below, the replay move panel narrows to (260px), Coach to (330px), and the gaps to (20px).
- At (1120px) and below, Coach moves below the board and aligns with its column; the move panel remains beside the board.
- At (960px) and below, page side padding becomes (24px), game columns tighten, and the replay gap becomes (24px).
- In side-by-side replay layouts above (900px) wide and at most (1000px) tall, the board cap reduces to (720px). Replay top padding becomes (16px), navigation bottom padding (10px), and navigation and game-heading bottom margins (14px), saving vertical space on laptops while retaining the existing text sizes.
- At (760px) and below, replay becomes one column. The move panel follows the board controls with a (16px) top margin and a fixed (280px) height; Coach follows below. The heading and Back to games link align with the single column.
- At (700px) and below, the header wraps into two rows with a minimum height of (108px) and padding of (12px 18px 0). The full-width second row keeps both navigation links visible with targets at least (44px) tall. The account button stays beside the brand with a minimum (44px) height and truncates long usernames; its chevron is hidden. Library side padding becomes (18px), and sync status moves below the title. Filters sit below search. Game rows place their analysis actions on the right with date beneath the opponent metadata. The list caps at (520px).
- At (700px) and below, Lessons stacks its heading and controls with a (16px) gap, uses a (32px) title, and stacks the coverage summary. Overview buttons retain two columns with a (12px) gap and (18px 16px) padding; their headings become (18px) and totals (32px). Topic summaries use (16px 8px) padding and filters use (13px) text. At (440px) and below, overview buttons and loading placeholders stack into one column, card padding becomes (18px), and the explorer heading may wrap. Filter text becomes (12px) with (4px) grid gaps, preserving two tactical choices and four full severity labels; controls retain a minimum (44px) height. Severity breakdowns and legends wrap naturally.
- At (700px) and below, Multi-game analysis stacks its heading and action, makes the saved-response selector full width beneath Coach responses, and reduces report prose to (15px). At (440px) and below, its title becomes (30px) and Run analysis fills the available width. The refresh control remains beside the wrapping sample counts; report text and metadata wrap without horizontal overflow.
- At (700px) and below, replay uses one column. Replay side padding and response body padding are (16px). Candidate rows and stronger-move links retain touch targets at least (44px) tall.
- At (370px) and below, spacing and replay controls tighten and response padding becomes (14px). The body has no fixed minimum width, so (320px) viewports accommodate the scrollbar without horizontal overflow.

## Elevation & Depth

The implementation has no shadows. Thin borders and tonal hover or selection fills establish hierarchy on the pure-black workspace and panels. Interactive feedback is a color change, not movement or elevation. The account dialog dims the page with a translucent black backdrop (#000000b8); its border defines the modal without a shadow.

## Shapes

The board has square outer corners to match the reference. Player tokens retain (3px) corners; result labels use the move radius; icon controls, selected candidates, inputs, and actions use (8px) corners. Account dialog, library, Coach, and replay overview containers use (12px) corners; status blocks use (6px). Game rows remain flat with horizontal dividers. Section boundaries and field outlines use fine (1px) borders.

## Components

### Buttons and focus

Primary actions use soft white with charcoal labels; account submission includes a trailing arrow. Replay play/pause uses a neutral tonal fill in a compact icon control. Secondary retry actions use pure black with an outline. Text actions have no container and underline on hover. Icon controls are transparent until hovered. Disabled buttons use reduced opacity (.42) and a default cursor.

Button color transitions take (140ms). Interactive focus uses a solid blue outline (2px) with an offset (4px). Sync and loading spinners rotate over (1s); reduced-motion preference removes animations and transitions.

### Inputs and filters

Pure-black fields use clearly visible grey borders and gently curved corners. The account dialog has a full-width username field with (10px 12px) padding and a minimum (46px) height. Search has a leading icon, while native select controls handle speed and result. Keep visible labels or accessible names on all fields.

### Primary navigation

The persistent header contains real links to Your game library and Lessons. Muted (13px) labels and compact outline SVG icons sit (8px) apart within links; the links are separated by (24px). Hover uses soft white, while the current page combines soft white with a blue bottom rule (2px) and `aria-current="page"`. Replay keeps the library tab current. Existing keyboard focus remains visible. The header gap between brand and navigation is (40px), reducing to (24px) at (960px); its mobile treatment is defined in Layout.

Dev is a separate header link beside account settings, with the same muted type, soft-white hover, blue current-page rule, and visible focus. Its minimum target height is (44px); the code icon disappears at (720px) and below. The account label disappears at (420px) and below while its accessible name remains.

### Account settings

One outlined account button at the right of the persistent header identifies the current username, or Account before setup. It uses the established control radius, muted outline icons, a neutral hover fill, and ellipsis for long names. The desktop target has a minimum (40px) height and maximum (240px) width; mobile uses a minimum (44px) height.

The native modal dialog centers within the viewport, caps its width at (440px), retains (16px) viewport clearance, and scrolls internally when needed. Its pure-black surface uses a fine field-colored border, panel corners, and (28px) padding, reduced to (24px) at (700px). A visible username label and public-games hint precede the full-width Add account or Save account action. Saved accounts use flat, full-width buttons with a minimum (44px) height and a check for the current account. The close control is (44px) square. Opening focuses the username; Tab stays inside, Escape or the backdrop closes it, and closing returns focus to the opener.

### Dev reset controls

Dev shares the library width and heading hierarchy. Fine rules bound Clear all analysis above the searchable Clear one game list. Desktop rows align player names, date, and an outlined action; metadata uses muted tabular text. At (720px) and below, the bulk action stacks beneath its description and dates move beneath player metadata. At (420px) and below, each row's action occupies a third line and the all-accounts label stacks under its heading. Long names wrap, preserving the layout at (320px).

Clear all and final confirmation use the existing coral palette, control corners, (10px 16px) padding, and minimum (44px) height. Per-game entry uses the secondary outline. Both open a native modal using the account dialog's dimensions, border, backdrop, and spacing. Its text identifies the target, removed analysis, and preserved original games. Cancel receives initial focus; Escape cancels, and cancelling restores focus to the opener. Actions wrap with a (12px) gap.

Loading and pending resets disable conflicting actions. A polite live region reports progress and success; failures use an alert with an icon and text. Load errors offer Try again, an empty library explains how to add games, and unmatched searches offer Clear search. Resetting does not trigger analysis.

### Lessons category explorer

Two pure-black overview buttons use the established panel corners and fine borders. Each combines a category heading, prominent total, segmented severity bar, and a written severity summary. The selected button adds a sky-blue border and filled check indicator; hover brightens the border. Both expose their pressed state and control the same explorer. The Tactical total combines Missed tactics and Allowed tactics, which remain separate choices inside the explorer. Positional topics identify the piece in Stockfish’s best move. Unclassified errors use a separate quiet button with a count and chevron, never merged into another group.

Tactical subgroup and severity filters are native buttons with pressed states and minimum (44px) height. The selected tactical choice uses the existing blue selection fill; the selected severity uses a neutral hover fill. The matching total updates in a polite live region. Filtering uses saved counts to remove zero-match topics, sort by matching count with alphabetical ties, and recompute each bar as a share of the matching set.

Each topic is a native details/summary disclosure with its name on the left, count and chevron on the right, and a thin sky-blue proportion bar below. Hover adds a neutral fill; opening rotates the chevron and reveals the matching proportion and the topic's complete severity breakdown, including zeros. Text gives the bar's percentage to assistive technology. Disclosures show aggregate counts rather than individual move lists. The summary uses the established control radius and visible keyboard focus; its color and chevron transitions take (140ms) and respect reduced-motion preference.

Account selection uses the global dialog; the local refresh control retains a minimum (44px) target. Loading uses two overview placeholders and one full-width explorer placeholder. Errors offer retry; the empty state links to the game library. A filter with no matches explains the result and offers Show all severities. Unclassified detail offers a library link for adding categories. Earlier-review and pending-review notices appear below the explorer as neutral text with blue links, followed by the counting rule; these notices are not success states.

### Multi-game analysis report

The screen extends the existing black surfaces, DM Sans, white primary actions, and blue links without adding design tokens. Run analysis is an explicit action, disabled while data is unavailable or a request is starting, queued, or running. Active requests show a spinner and plain-language status while retaining the previous report. Failures appear inline; data-loading failures include Try again. Empty states explain missing analyzed mistakes or the absence of saved responses and provide the applicable next action.

The native Saved analysis selector lists completed responses by local date, time, and game count, identifying the newest as Latest. Completing a run selects its saved response automatically. Metadata beneath the selector gives the games, evaluated moves, and errors captured at the time of that response. Local refresh and response controls retain accessible labels, visible keyboard focus, and minimum (44px) targets. The shared account dialog supplies player selection.

The report opens with an overall assessment, followed by Decision-making patterns and Foundations to develop when present. Each pattern pairs a title with written confidence, explanatory prose, and a Try this in your next game adjustment. An ordered practice list gives the foundation, reason, Practice focus, and related pattern titles. Fine dividers and spacing establish hierarchy without additional cards; internal pattern and position identifiers are not displayed.

### Library rows and result markers

Each semantic list item contains a Win/Loss/Draw badge, opponent, rating, played color, time control, date, and separate Analyze game and Open game actions. Analyze game starts engine-only analysis and becomes a disabled progress action while queued or running. Completed rows offer Review game and a compact count of move grades; interrupted rows offer Resume analysis. Saved progress and errors appear below the metadata. Rows are not whole-row buttons. Actions use a quiet outline and dark blue hover fill, with accessible names identifying the opponent. Long names wrap. On mobile, metadata rearranges beneath the opponent and action without horizontal scrolling.

### Replay navigation and Coach

Flip, first, previous move, play/pause, next move, and final controls sit below the board. Every forward/back click advances exactly one half-move, including opponent turns, without an intermediate preview or delayed transition. Starting and final positions remain reachable for either colour and custom Black-to-move starts. Board orientation does not change navigation.

The slider selects every half-move while the counter retains the actual PGN index and a visually hidden live region announces the side to move or final position. Bookmarks preserve exact opponent turns. Rapid clicks advance from the current position. Autoplay rests for (850ms) at each half-move; manual navigation pauses it, and Space toggles playback without hiding an already revealed review. The replay omits the keyboard hint, last-move caption, date/time-control subtitle, result badge, and Replay & explore label.

The game overview replaces the scrollable move list in the same desktop column and follows the board height. Its top graph uses a purple line and translucent purple fill around a neutral baseline, a current-position marker, and severity dots. A keyboard-accessible range control navigates the graph. The middle summary keeps White on the left and Black on the right, with names, colour tokens, accuracy and four move counts: Good, Inaccuracy, Mistake and Blunder. The bottom section shows position sharpness with its 0–100 score and Lichess phase, then the recorded move played next, its elapsed time and its mover-perspective evaluation. Container queries compact spacing for smaller boards without an internal scrollbar; mobile places the overview below the controls at natural height. Pure-black surfaces and existing chess artwork remain unchanged. Purple accents are scoped to the replay workspace.

Green Previous review and Next review controls sit below the coaching response, separated by a fine top rule and (16px) spacing. Labels use (12px) text beside chevrons; controls have (44px) minimum height, (8px) corners, and a dark green hover fill. Endpoints disable the unavailable direction. These arrows visit only the selected player's inaccuracies, mistakes, and blunders with a matching saved coach response. A jump reveals the full response and played-move assessment directly, bypassing practice for that visit; ordinary move navigation keeps the existing practice flow.

The Coach response is one compact outlined card without tabs. The heading sits directly above it with Coach and an info icon for saved response details. The model selector and Run coach button are omitted. Idle saved-status text and the redundant Coach response label are omitted; active requests and failures still show status messages. The card starts near the top of the board.

An engine-only result renders just the Moves section in the existing coaching card. It contains the first three Stockfish choices plus the recorded move as a fourth row only when it is outside those three, with scores and severity but no generated explanations. Opponent turns use the heading Opponent’s moves and mark their recorded choice Opponent move. Each score retains its mover's perspective. Board selection derives arrows and highlights from UCI. Coach feedback adds the position explanation without a separate needs or plan section. Partial analysis updates do not reset the replay position or board selection. Older analyses without complete opponent coverage show Analyze remaining moves; missing scores remain unavailable until saved evidence arrives.

When practice is available, its exercise card contains the heading Find a better move than {SAN} and the short `position_overview`, typed incrementally without revealing candidate explanations. A thin purple arrow (#9565df) depicts the recorded move played immediately after the shown board, during both practice and normal replay. It adds no square recolouring and disappears during a variation or attempted-move preview, and at the final position. Candidate previews retain their existing instructional highlights. Attempt feedback and errors appear below the card when needed. A correct move receives brief success feedback, then the hint fades and collapses automatically. The review expands into place: Understand the position types `position_explanation`, followed by the automatically selected original move's explanation. The completed hint and View review button are absent. Show all finishes both queued explanations; previously read passages appear immediately, with completion saved locally by response and content. Reduced motion shows full text immediately and skips spatial animation. Text reserves its final line wrapping; screen readers receive complete text without per-character announcements. Recognized SAN moves appear as whole native buttons within the prose, using muted purple, an underline, inherited type, and visible keyboard focus. Hover and expanded states add the existing dark purple selection fill. The new format has no candidate list; the inline original move retains access to its assessment.

Under the board slider, small amber, orange, and red markers identify the selected player's inaccuracies, mistakes, and blunders. Good and uncertain moves are unmarked. Hover/focus tooltips and accessible labels give meaning beyond color; the visible legend and turn caption are omitted. Marker placement follows the full half-move timeline; clicking jumps to the pre-move decision and pauses replay.

The sharpness tag and a visible 0–100 score live in the left sidebar's Position section. Forgiving uses muted green, Flexible purple, Selective lavender, Demanding amber, and Critical coral. The tooltip and accessible description explain evaluation differences among Stockfish's top five moves. Tags use the unchanged unrounded cutoffs at 20/40/60/80. Terminal positions, fewer than five legal moves, and incomplete evidence use neutral labels; mate scores can be classified with the ±10-pawn cap. Classification is computed by the backend from saved Stockfish evidence, including compatible older saves. Earlier coaching prose gets a separate refresh notice; loading it makes no model request.

Mistake taxonomy classification remains saved for internal analytics. It does not appear as lesson content or category/subcategory tags in the replay coaching card. The original move's severity and the position's decision tag retain their separate roles.

Move detail stays hidden until a SAN button or move row is selected. One shared panel below the explanation and original move control shows the selected move's reason or original-move assessment, its own score when available, and any stronger-candidate comparison. Saved engine continuations add wrapping step buttons beginning with Position; the active step exposes its pressed state. Legacy teaching falls back to its positional thesis and collapsed Moves rows, while older Markdown remains readable. The original move appears once in that fallback: a matching recommendation receives its Player move identity, or an unlisted played move becomes the final row. The stored candidate pool and ordering do not change.

An independent “Tactic classification” footer follows the review and selected move detail in both coached and engine-only reviews. It uses (13px) body text, a muted label, (20px) top margin, (16px) top padding, the existing fine top border, and natural wrapping. Missed and allowed motifs can appear together. Missing, incomplete, ineligible, and unmatched results have distinct short messages; partial findings retain an explicit line-evidence qualifier. The footer reads saved ingestion results and never starts analysis on navigation. It stays hidden with the rest of the review until View review is selected after practice.

Move rows place SAN and optional Player move and quality indicators on the left, with the evaluation and board-preview icon on the right. Positive side-to-move scores use green, negative scores muted red, and near-equal or bounded scores slate; tooltip and accessible labels identify perspective and meaning. Missing engine evidence stays blank. The original move retains a blue Player move badge and dark blue row fill without a left stripe. Player severity labels are Good, Inaccuracy, Mistake, Blunder, or Quality uncertain. Good uses green, Inaccuracy amber, and Mistake/Blunder muted red with stronger weight for Blunder. The label tooltip explains the logistic winning-chance loss or mate transition. Severity remains separate from the blue identity marker and the unchanged position decision tag.

The selected row adds a blue (1px) outline and dark blue fill; keyboard focus remains a distinct (2px) outline. Selecting an inline move or row pauses autoplay, opens its detail, and shows two highlighted squares and an arrow on the root position without playing the move. Each bracketed SAN excerpt in a move explanation is one inline variation link. Clicking it autoplays only the relevant excerpt at one ply per second, then holds the final position. A compact status below the board provides Back to game and Replay; returning restores the original game position and candidate annotations. Missing or ambiguous excerpts remain plain text. The full engine-continuation list and comparison button are omitted. Selecting the same move again collapses its detail and clears its annotations; navigation, new responses, and transient replay states reset selection. The separate explanation and Clear strip below the board is omitted. The board layout and controls retain their established styling. Missing practice summaries or older feedback show descriptive notices. No second-node essay is displayed.

The card uses (16px) padding, Times New Roman (17px) body text, 1.6 line height, and (18px) headings. The practice card and selected move details use the same body type and heading scale. Consecutive sections and selected move details have (20px) top margin, (16px) top padding, and a fine divider. Move rows use (12px 8px) padding with fine horizontal rules. Below (370px), both cards use (14px) padding; heading tags and move labels wrap naturally, and coarse-pointer variation controls remain at least (44px) tall. Repeated engine-source text and Show on board labels are replaced by row icons. Raw HTML and embedded Markdown images remain excluded.

Coaching is prepared through game analysis in the library. The replay has no model selection or manual generation controls. The info icon reveals the saved model, position, and timestamp on hover or focus; analysis progress and failures appear inline. The header omits the Saved on this device label. The question field and its draft persistence have been removed.


Keyboard arrows, Home, End, and Space support replay without intercepting typing in fields or interaction inside the Coach content. Factor summaries retain native Enter/Space activation and visible keyboard focus. Focused buttons keep their native Space activation.

Markdown blockquotes use a neutral (2px) quotation rule. This is an intentional exception to the detector's side-accent warning: it marks quoted prose, not a card or status callout.

### Board and player bars

Locally bundled Classic PNG pieces occupy each cell of an eight-by-eight CSS grid. Each square samples its corresponding tile from the full Icy Sea texture using an 800% background size. All twelve piece images and the texture are in `frontend/public/assets/chess/`; `SOURCES.json` records provenance. The header knight remains the original SVG.

Coordinates remain at the board's left and bottom edges after flipping. They use the opposite square color and scale with board width, matching the supplied reference. Their lower contrast is an intentional reference-matching exception confined to board coordinates; the existing accessible position summary is retained. Player bars follow orientation and show names, ratings, and piece colours without a You label; a visually hidden live region announces position changes.

### Status and empty states

Library sync uses muted (12px) status text and a small icon beside the title, announced through a polite live region. Saved games remain visible and usable during checks and refreshes. Sync failures add warning-colored iconography and a short notice between fine rules with Try again and Account settings actions; the notice confirms that existing games remain available. Before setup, a centered invitation opens the account dialog. A configured account with no games shows finding, failure, or no-completed-games copy as appropriate; a filtered-empty list offers Clear filters. These states use the established typography and no decorative board. Replay keeps Back to games available during loading and errors.

## Do's and Don'ts

### Do:
- **Do** preserve the approved pure-black workspace and panels, blue-grey board, and compact library.
- **Do** keep the board, move list, slider, accessible position announcement, and coaching synchronized to the actual PGN half-move, including opponent turns.
- **Do** use text alongside result and status colors.
- **Do** preserve visible keyboard focus and the implemented reduced-motion behavior.
- **Do** retain the locally bundled DM Sans, reference-matched board assets, and original header icon.

### Don't:
- **Don't** imply affiliation with Chess.com; keep the reference-matched artwork's source and ownership documented.
- **Don't** add decorative shadows or floating cards to the existing flat workspace.
- **Don't** let selection hide the distinction between last move and check.
- **Don't** replace a truthful empty library with invented game records.
