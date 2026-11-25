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
    fontFamily: "'DM Sans Variable', sans-serif"
    fontSize: "14px"
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
    height: "44px"
    padding: "0px 36px 0px 12px"
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

This records the implemented import and replay UI and the user's approved replacement of the light workspace with a dark theme. Pure-black canvas and panels, blue selection, and white primary actions define the surrounding interface. The board artwork follows the user's November 15, 2026 reference and retains its established texture and pieces.

**Key Characteristics:**
- Dark, flat surfaces separated by fine rules and tonal changes.
- An Icy Sea textured board with Classic black-and-white pieces, matching the supplied reference.
- Compact game rows and precise move selection.
- DM Sans throughout, with compact coaching prose and working controls.

## Colors

The palette is cool and muted, with semantic colors reserved for game and request state. Frontmatter contains the normative values; the sidecar's generated tonal ramps are preview metadata, not additional implementation tokens.

### Primary

Soft white identifies primary actions such as Import games and Run coach, with charcoal labels and a slightly darker hover state. Muted sky blue identifies text actions, keyboard focus, and selected move outlines. Replay play/pause uses a neutral tonal fill.

### Neutral

The workspace, panels, and fields share a pure jet-black (#000000) background. Soft white carries headings and controls, lighter grey carries coaching prose, and muted grey carries supporting text. Subtle rules divide sections; brighter field borders define interactive controls. Dark blue fills identify selections and the Analyze hover state. The header shares the workspace canvas.

### Semantic and board colors

The locally bundled Icy Sea image supplies the board's textured light and blue squares; board color tokens are fallback colors. Translucent olive marks the last move and muted coral marks check, preserving the texture beneath each highlight. Wins use light sage on dark green, losses and errors use light coral on dark clay, and draws use muted grey on a neutral fill, always accompanied by text. Amber on dark ochre marks a clear decision preference.

**The Position State Rule.** Keep last-move squares and check distinguishable, and announce the settled side to move or final position to screen readers.

Lessons segmented bars and severity dots use warning amber for Inaccuracy, warm orange for Mistake, and the existing negative coral for Blunder. Text summaries, named breakdowns, and a legend explain every severity color; counts remain neutral. Sky blue identifies the selected overview card and proportional topic bars. These severity roles match the library counts; the replay timeline retains its distinct stronger red Blunder marker.

## Typography

Locally bundled DM Sans Variable supplies all headings, controls, names, metadata, and notation. The game-title separator uses the same family at regular weight. Newsreader is no longer imported.

The library title is (38px), saved-games heading (19px), opponent names (14px), and working controls (12-14px). At narrow widths the library title becomes (32px) and game titles (23px). Below (370px), the library title becomes (29px). Coach prose uses (14px) text at (1.6) line height with a maximum line length of (72ch); section headings use (15px) and the Coach title (16px). Candidate explanations use (13px), SAN (14px), and score chips (12px). Counts, dates, and evaluations use tabular numerals where applicable.

Lessons reuses the display title, with its own heading and total roles from the frontmatter. Topic labels use (16px) at (550) weight, while supporting descriptions and matching counts use (13px). Overview totals and all breakdown counts use tabular numerals. Mobile size changes are recorded in Layout.

Multi-game analysis uses the same DM Sans hierarchy. Report prose is (16px) with a (1.75) line height and a maximum line length of (75ch). Section headings use (21px), pattern and practice titles (17px), and thinking-adjustment labels (13px) in the existing light blue accent. Confidence and saved-sample metadata use muted (12px) text.

## Layout

The app has library, replay, and Lessons screens. The root URL opens the game library without a board. The library is centered at a maximum outer width of (1120px), with (38px 36px 24px) padding. A (68px) canvas-colored header sits above it. A short title leads into one compact import form, then saved-player selection, search, filters, and a scrollable list. Desktop rows align result, opponent, time control, date, and Analyze in columns.

Lessons shares the library container. Its title and player/refresh controls sit opposite each other with a (24px) gap and (28px) space before the content. A compact error count and library-coverage summary precede two equal-width Positional and Tactical overview buttons with an (18px) separation and a (16px) grid gap. A separate Unclassified row appears below when needed. A fine rule introduces the explorer, with (20px) outer separation and (28px) top padding. Tactical subgroup controls form two equal columns; severity filters form four. Topic disclosures occupy the full width beneath them. Coverage notes follow after (28px), separated by a rule and (18px) top padding.

The Lessons heading includes a secondary Multi-game analysis link to `#lessons/multi-game`. This screen shares the library container and places Back to lessons above the title and primary Run analysis action. An inline player/refresh group and wrapping saved-sample counts sit above a fine rule. Coach responses begins after (32px), with a labeled saved-response selector opposite its heading. The report follows as unboxed prose; major sections have (36px) separation, (28px) top padding, and a fine divider.

Analyze opens a hash route containing the game ID and player. The dedicated replay screen has a maximum outer width of (2000px), a Back to games link, game heading, board, and Coach panel. The board caps at (840px), with a (400px) Coach sidebar and a (32px) gap. A flexible empty leading track balances the sidebar track on wide displays, centering the board itself in the viewport. As space narrows, that leading track yields first, then the board scales to the remaining width. The game heading and Back to games link follow the board's left edge. Inside Coach, one outlined response panel spans the available width. Position teaching, the original move control, and selected move detail share one card; the existing exercise card precedes it when practice is available. The panel grows with its content and the page scrolls naturally. Browser navigation and direct replay links work. Returning within the session restores filters, list/page scrolling, and focus to the originating Analyze link. Replay position remains saved per game.

- At (960px) and below, page side padding becomes (24px), game columns tighten, and the replay gap becomes (24px).
- At (900px) and below, Coach moves below the centered board; both columns share an (840px) maximum width and the combined response remains one panel.
- At (700px) and below, the header wraps into two rows with a minimum height of (108px) and padding of (12px 18px 0). The full-width second row keeps both navigation links visible with targets at least (44px) tall. Library side padding becomes (18px), and import controls wrap under the username. Filters sit below search. Game rows place their Analyze link on the right with date beneath it. The list caps at (520px).
- At (700px) and below, Lessons stacks its heading and controls with a (16px) gap, uses a (32px) title, and stacks the coverage summary. Overview buttons retain two columns with a (12px) gap and (18px 16px) padding; their headings become (18px) and totals (32px). Topic summaries use (16px 8px) padding and filters use (13px) text. At (440px) and below, overview buttons and loading placeholders stack into one column, card padding becomes (18px), and the explorer heading may wrap. Filter text becomes (12px) with (4px) grid gaps, preserving two tactical choices and four full severity labels; controls retain a minimum (44px) height. Severity breakdowns and legends wrap naturally.
- At (700px) and below, Multi-game analysis stacks its heading and action, makes the saved-response selector full width beneath Coach responses, and reduces report prose to (15px). At (440px) and below, its title becomes (30px) and Run analysis fills the available width. Player selection and refresh remain an inline group while sample counts wrap; report text and metadata wrap without horizontal overflow.
- At (700px) and below, replay uses one column. Replay side padding and response body padding are (16px). Candidate rows and stronger-move links retain touch targets at least (44px) tall.
- At (370px) and below, spacing and replay controls tighten and response padding becomes (14px). The body has no fixed minimum width, so (320px) viewports accommodate the scrollbar without horizontal overflow.

## Elevation & Depth

The implementation has no shadows. Thin borders and tonal hover or selection fills establish hierarchy on the pure-black workspace and panels. Interactive feedback is a color change, not movement or elevation.

## Shapes

The board has square outer corners to match the reference. Player tokens retain (3px) corners; result labels use the move radius; icon controls, selected candidates, inputs, and actions use (8px) corners. Import, library, and Coach containers use (12px) corners; status blocks use (6px). Game rows remain flat with horizontal dividers. Section boundaries and field outlines use fine (1px) borders.

## Components

### Buttons and focus

Primary actions use soft white with charcoal labels; import includes a trailing arrow. Replay play/pause uses a neutral tonal fill in a compact icon control. Secondary retry actions use pure black with an outline. Text actions have no container and underline on hover. Icon controls are transparent until hovered. Disabled buttons use reduced opacity (.42) and a default cursor.

Button color transitions take (140ms). Interactive focus uses a solid blue outline (2px) with an offset (4px). Import and loading spinners rotate over (1s); reduced-motion preference removes animations and transitions.

### Inputs and filters

Pure-black fields use clearly visible grey borders and gently curved corners. The username field reserves room for its clear control. Search has a leading icon, while native select controls handle imported player, import count, speed, and result. Keep visible labels or accessible names on all fields.

### Primary navigation

The persistent header contains real links to Your game library and Lessons. Muted (13px) labels and compact outline SVG icons sit (8px) apart within links; the links are separated by (24px). Hover uses soft white, while the current page combines soft white with a blue bottom rule (2px) and `aria-current="page"`. Replay keeps the library tab current. Existing keyboard focus remains visible. The header gap between brand and navigation is (40px), reducing to (24px) at (960px); its mobile treatment is defined in Layout.

### Lessons category explorer

Two pure-black overview buttons use the established panel corners and fine borders. Each combines a category heading, prominent total, segmented severity bar, and a written severity summary. The selected button adds a sky-blue border and filled check indicator; hover brightens the border. Both expose their pressed state and control the same explorer. The Tactical total combines Missed tactics and Allowed tactics, which remain separate choices inside the explorer. Positional topics identify the piece in Stockfish’s best move. Unclassified errors use a separate quiet button with a count and chevron, never merged into another group.

Tactical subgroup and severity filters are native buttons with pressed states and minimum (44px) height. The selected tactical choice uses the existing blue selection fill; the selected severity uses a neutral hover fill. The matching total updates in a polite live region. Filtering uses saved counts to remove zero-match topics, sort by matching count with alphabetical ties, and recompute each bar as a share of the matching set.

Each topic is a native details/summary disclosure with its name on the left, count and chevron on the right, and a thin sky-blue proportion bar below. Hover adds a neutral fill; opening rotates the chevron and reveals the matching proportion and the topic's complete severity breakdown, including zeros. Text gives the bar's percentage to assistive technology. Disclosures show aggregate counts rather than individual move lists. The summary uses the established control radius and visible keyboard focus; its color and chevron transitions take (140ms) and respect reduced-motion preference.

Player selection and refresh reuse existing controls with minimum (44px) targets. Loading uses two overview placeholders and one full-width explorer placeholder. Errors offer retry; the empty state links to the game library. A filter with no matches explains the result and offers Show all severities. Unclassified detail offers a library link for adding categories. Earlier-review and pending-review notices appear below the explorer as neutral text with blue links, followed by the counting rule; these notices are not success states.

### Multi-game analysis report

The screen extends the existing black surfaces, DM Sans, white primary actions, and blue links without adding design tokens. Run analysis is an explicit action, disabled while data is unavailable or a request is starting, queued, or running. Active requests show a spinner and plain-language status while retaining the previous report. Failures appear inline; data-loading failures include Try again. Empty states explain missing analyzed mistakes or the absence of saved responses and provide the applicable next action.

The native Saved analysis selector lists completed responses by local date, time, and game count, identifying the newest as Latest. Completing a run selects its saved response automatically. Metadata beneath the selector gives the games, evaluated moves, and errors captured at the time of that response. Player, refresh, and response controls retain accessible labels, visible keyboard focus, and minimum (44px) targets.

The report opens with an overall assessment, followed by Decision-making patterns and Foundations to develop when present. Each pattern pairs a title with written confidence, explanatory prose, and a Try this in your next game adjustment. An ordered practice list gives the foundation, reason, Practice focus, and related pattern titles. Fine dividers and spacing establish hierarchy without additional cards; internal pattern and position identifiers are not displayed.

### Library rows and result markers

Each semantic list item contains a Win/Loss/Draw badge, opponent, rating, played color, time control, date, and separate Analyze game and Open game actions. Analyze game starts engine-only analysis and becomes a disabled progress action while queued or running. Completed rows offer Review game and a compact count of move grades; interrupted rows offer Resume analysis. Saved progress and errors appear below the metadata. Rows are not whole-row buttons. Actions use a quiet outline and dark blue hover fill, with accessible names identifying the opponent. Long names wrap. On mobile, metadata rearranges beneath the opponent and action without horizontal scrolling.

### Replay navigation and Coach

Flip, first, previous turn, play/pause, next turn, and final controls sit below the board. Replay stops at the imported player's decision points, determined from the FEN side to move. A normal forward/back step briefly shows the intervening board for (100ms), then settles two half-moves away. Black's first forward step from the standard starting position advances only one half-move. Starting and final positions remain reachable for either colour. Board orientation does not change which player's turns are followed.

The slider selects these same decision points while the counter retains the actual PGN half-move and a visually hidden live region announces the side to move or final position. Older bookmarks on an opponent's turn restore to the preceding player decision. Coach content and the announced position remain at the previous settled position during the brief board preview, and Run coach is disabled until it finishes. Rapid clicks advance from the pending destination; obsolete transition timers cannot overwrite newer input. Autoplay rests for (850ms) at each decision, then follows the same step sequence. Manual navigation pauses it. Pausing during a preview completes that pair before resting. Reduced-motion preference skips the intermediate board. The replay omits the keyboard hint, last-move caption, date/time-control subtitle, result badge, and Replay & explore label.

The Coach response is one compact outlined card without tabs. The toolbar sits directly above it with Coach, an info icon for saved response details, the model selector, and Run coach; its groups wrap when space is limited. Idle saved-status text and the redundant Coach response label are omitted; active requests and failures still show status messages. The card starts near the top of the board.

An engine-only result renders just the Moves section in the existing coaching card. It contains the first three Stockfish choices plus a separate player row only when necessary, with scores and the player's severity but no generated explanations. Board selection derives arrows and highlights from UCI. Coach feedback adds the position explanation without a separate needs or plan section. Partial analysis updates do not reset the replay position or board selection.

When practice is available, its existing exercise card shows the short `position_overview` before attempts and keeps it after Exercise complete. The overview introduces the position without revealing candidate explanations. View review reveals the coaching card, whose Understand the position section renders `position_explanation`. Recognized SAN moves are native buttons within the prose, using muted blue, an underline, inherited type, and visible keyboard focus. Hover and expanded states add the existing dark blue selection fill. The new format has no candidate list; a Your move control retains access to the original move's assessment.

Under the board slider, small amber, orange, and red markers identify inaccuracies, mistakes, and blunders. Good and uncertain moves are unmarked. Hover/focus tooltips and accessible labels give meaning beyond color; the visible legend and turn caption are omitted. Marker placement uses the same player-turn stops as the slider; clicking jumps to the pre-move decision and pauses replay.

Understand the position has a small sharpness tag on the same heading row: Forgiving uses muted green, Flexible blue, Selective lavender, Demanding amber, and Critical coral. The tooltip and accessible description include the normalized 0–100 score and explain evaluation differences among Stockfish's top five moves. Tags use unrounded cutoffs at 20/40/60/80. Terminal positions, fewer than five legal moves, and incomplete evidence use neutral labels; mate scores can be classified with the ±10-pawn cap. Classification is computed by the backend from saved Stockfish evidence. Earlier coaching prose gets a separate refresh notice; loading it makes no model request.

Mistake taxonomy classification remains saved for internal analytics. It does not appear as lesson content or category/subcategory tags in the replay coaching card. The original move's severity and the position's decision tag retain their separate roles.

Move detail stays hidden until a SAN button or move row is selected. One shared panel below the explanation and original move control shows the selected move's reason or original-move assessment, its own score when available, and any stronger-candidate comparison. Saved engine continuations add wrapping step buttons beginning with Position; the active step exposes its pressed state. Legacy teaching falls back to its positional thesis and collapsed Moves rows, while older Markdown remains readable. The original move appears once in that fallback: a matching recommendation receives its Player move identity, or an unlisted played move becomes the final row. The stored candidate pool and ordering do not change.

An independent “Tactic classification” footer follows the review and selected move detail in both coached and engine-only reviews. It uses (13px) body text, a muted label, (20px) top margin, (16px) top padding, the existing fine top border, and natural wrapping. Missed and allowed motifs can appear together. Missing, incomplete, ineligible, and unmatched results have distinct short messages; partial findings retain an explicit line-evidence qualifier. The footer reads saved ingestion results and never starts analysis on navigation. It stays hidden with the rest of the review until View review is selected after practice.

Move rows place SAN and optional Player move and quality indicators on the left, with the evaluation and board-preview icon on the right. Positive side-to-move scores use green, negative scores muted red, and near-equal or bounded scores slate; tooltip and accessible labels identify perspective and meaning. Missing engine evidence stays blank. The original move retains a blue Player move badge and dark blue row fill without a left stripe. Player severity labels are Good, Inaccuracy, Mistake, Blunder, or Quality uncertain. Good uses green, Inaccuracy amber, and Mistake/Blunder muted red with stronger weight for Blunder. The label tooltip explains the logistic winning-chance loss or mate transition. Severity remains separate from the blue identity marker and the unchanged position decision tag.

The selected row adds a blue (1px) outline and dark blue fill; keyboard focus remains a distinct (2px) outline. Selecting an inline move or row pauses autoplay, opens its detail, and shows two highlighted squares and an arrow on the root position without playing the move. Selecting a saved engine step changes the board to that continuation position; Position restores the root and its annotations. Selecting the same move again collapses its detail and clears its annotations; navigation, new responses, and transient replay states reset selection. The separate explanation and Clear strip below the board is omitted. The board layout and controls retain their established styling. Missing practice hints or older feedback invite a rerun. No second-node essay is displayed.

The card uses (16px) padding, (14px) body text, 1.6 line height, and (15px) headings. The practice card uses the same padding, body type, and heading scale; selected move details also use (15px) headings. Consecutive sections and selected move details have (20px) top margin, (16px) top padding, and a fine divider. Move rows use (12px 8px) padding and (13px) explanations, with fine horizontal rules. Below (370px), both cards use (14px) padding; heading tags and move labels wrap naturally, and coarse-pointer comparison links remain at least (44px) tall. Repeated engine-source text and Show on board labels are replaced by row icons. Raw HTML and embedded Markdown images remain excluded.

The dropdown offers GPT-6 Astra and GPT-6.1 Terra, defaults to Astra, remembers the selection, and is disabled during a run. Both models use the same single-node, single-call flow. The info icon reveals the saved model, position, and timestamp on hover or focus. Changing model applies to the next run. Reruns retain the prior answer until success; failures appear inline. The question field and its draft persistence have been removed.


Keyboard arrows, Home, End, and Space support replay without intercepting typing in fields or interaction inside the Coach content. Factor summaries retain native Enter/Space activation and visible keyboard focus. Focused buttons keep their native Space activation.

Markdown blockquotes use a neutral (2px) quotation rule. This is an intentional exception to the detector's side-accent warning: it marks quoted prose, not a card or status callout.

### Board and player bars

Locally bundled Classic PNG pieces occupy each cell of an eight-by-eight CSS grid. Each square samples its corresponding tile from the full Icy Sea texture using an 800% background size. All twelve piece images and the texture are in `frontend/public/assets/chess/`; `SOURCES.json` records provenance. The header knight remains the original SVG.

Coordinates remain at the board's left and bottom edges after flipping. They use the opposite square color and scale with board width, matching the supplied reference. Their lower contrast is an intentional reference-matching exception confined to board coordinates; the existing accessible position summary is retained. Player bars follow orientation and identify the user's side; a visually hidden live region announces position changes.

### Status and empty states

Loading and import feedback combine short text with a small icon. Failures use an error surface or a plainly labeled retry action. The initial screen shows only import and game selection; empty libraries have a text invitation to import, with no decorative board. Replay keeps Back to games available during loading and errors. The library's empty and filtered-empty states explain what is missing and provide an applicable next action.

## Do's and Don'ts

### Do:
- **Do** preserve the approved pure-black workspace and panels, blue-grey board, and compact library.
- **Do** keep the settled board, slider, accessible position announcement, and coaching synchronized to the actual PGN half-move; only the board previews the intervening position during a turn transition.
- **Do** use text alongside result and status colors.
- **Do** preserve visible keyboard focus and the implemented reduced-motion behavior.
- **Do** retain the locally bundled DM Sans, reference-matched board assets, and original header icon.

### Don't:
- **Don't** imply affiliation with Chess.com; keep the reference-matched artwork's source and ownership documented.
- **Don't** add decorative shadows or floating cards to the existing flat workspace.
- **Don't** let selection hide the distinction between last move and check.
- **Don't** replace a truthful empty library with invented game records.
