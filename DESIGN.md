---
name: Chess study
description: A focused charcoal workspace for revisiting your games, one position at a time.
colors:
  primary: "#f1f2f4"
  primary-hover: "#d9dce1"
  focus: "#91b4d3"
  workspace: "#0c0d0f"
  surface: "#16181c"
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
    typography: "{typography.body}"
    rounded: "{rounded.panel}"
    padding: "24px"
  candidate-selected:
    backgroundColor: "{colors.selected-row}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "14px 12px"
  result-win:
    backgroundColor: "{colors.win-surface}"
    textColor: "{colors.win-ink}"
    rounded: "{rounded.move}"
    padding: "6px 10px"
  board:
    rounded: "{rounded.board}"
---

# Design System: Chess study

## Overview

**Creative North Star: "A focused study desk"**

A focused charcoal workspace gives the chess position a clear visual anchor while providing comfortable room for coaching. Blue-grey squares, soft white text, and a compact library support patient review. DM Sans carries headings and the working interface.

This records the implemented import and replay UI and the user's approved replacement of the light workspace with a dark theme. Near-black canvas, charcoal panels, blue selection, and white primary actions define the surrounding interface. The board artwork follows the user's November 15, 2026 reference and retains its established texture and pieces.

**Key Characteristics:**
- Dark, flat surfaces separated by fine rules and tonal changes.
- An Icy Sea textured board with Classic black-and-white pieces, matching the supplied reference.
- Compact game rows and precise move selection.
- DM Sans throughout, with spacious coaching prose and compact working controls.

## Colors

The palette is cool and muted, with semantic colors reserved for game and request state. Frontmatter contains the normative values; the sidecar's generated tonal ramps are preview metadata, not additional implementation tokens.

### Primary

Soft white identifies primary actions such as Import games and Run coach, with charcoal labels and a slightly darker hover state. Muted sky blue identifies text actions, keyboard focus, and selected move outlines. Replay play/pause uses a neutral tonal fill.

### Neutral

The near-black workspace surrounds charcoal panels and fields. Soft white carries headings and controls, lighter grey carries coaching prose, and muted grey carries supporting text. Subtle rules divide sections; brighter field borders define interactive controls. Dark blue fills identify selections and the Analyze hover state. The header shares the workspace canvas.

### Semantic and board colors

The locally bundled Icy Sea image supplies the board's textured light and blue squares; board color tokens are fallback colors. Translucent olive marks the last move and muted coral marks check, preserving the texture beneath each highlight. Wins use light sage on dark green, losses and errors use light coral on dark clay, and draws use muted grey on a neutral fill, always accompanied by text. Amber on dark ochre marks a clear decision preference.

**The Position State Rule.** Keep the position caption, last-move squares, and check distinguishable; each communicates a different part of the replay state.

## Typography

Locally bundled DM Sans Variable supplies all headings, controls, names, metadata, and notation. The game-title separator uses the same family at regular weight. Newsreader is no longer imported.

The library title is (38px), saved-games heading (19px), opponent names (14px), and working controls (12-14px). At narrow widths the library title becomes (32px) and game titles (23px). Below (370px), the library title becomes (29px). Coach prose uses (16px) text at (1.65) line height with a maximum line length of (72ch); section headings use (17px). Candidate explanations use (14px), SAN (16px), and score chips (13px). Counts, dates, and evaluations use tabular numerals where applicable.

## Layout

The app has two separate screens. The root URL opens the game library without a board. The library is centered at a maximum outer width of (1120px), with (38px 36px 24px) padding. A (68px) canvas-colored header sits above it. A short title leads into one compact import form, then saved-player selection, search, filters, and a scrollable list. Desktop rows align result, opponent, time control, date, and Analyze in columns.

Analyze opens a hash route containing the game ID and player. The dedicated replay screen has a maximum outer width of (1680px), a Back to games link, game heading, board, and Coach panel. The board caps at (620px). Board and Coach share the width in a 1:1.45 ratio with a (32px) gap. Inside Coach, one outlined response panel spans the available width. Position teaching, candidates, and move feedback share one card. The panel grows with its content and the page scrolls naturally. Browser navigation and direct replay links work. Returning within the session restores filters, list/page scrolling, and focus to the originating Analyze link. Replay position remains saved per game.

- At (1200px) and below, the board remains beside the single Coach response panel in a 1:1.35 ratio.
- At (960px) and below, page side padding becomes (24px), game columns tighten, and the replay gap becomes (24px).
- At (900px) and below, Coach moves below the centered board; the combined response remains one panel.
- At (700px) and below, the header becomes (64px), library side padding (18px), and import controls wrap under the username. Filters sit below search. Game rows place their Analyze link on the right with date beneath it. The list caps at (520px).
- At (700px) and below, replay uses one column. Replay side padding is (16px); the response body uses (18px) padding. Candidate rows and stronger-move links retain touch targets at least (44px) tall.
- At (370px) and below, spacing and replay controls tighten and response padding becomes (14px). The body has no fixed minimum width, so (320px) viewports accommodate the scrollbar without horizontal overflow.

## Elevation & Depth

The implementation has no shadows. Charcoal panels, the near-black workspace, thin borders, and tonal hover or selection fills establish hierarchy. Interactive feedback is a color change, not movement or elevation.

## Shapes

The board has square outer corners to match the reference. Player tokens retain (3px) corners; result labels use the move radius; icon controls, selected candidates, inputs, and actions use (8px) corners. Import, library, and Coach containers use (12px) corners; status blocks use (6px). Game rows remain flat with horizontal dividers. Section boundaries and field outlines use fine (1px) borders.

## Components

### Buttons and focus

Primary actions use soft white with charcoal labels; import includes a trailing arrow. Replay play/pause uses a neutral tonal fill in a compact icon control. Secondary retry actions use charcoal with an outline. Text actions have no container and underline on hover. Icon controls are transparent until hovered. Disabled buttons use reduced opacity (.42) and a default cursor.

Button color transitions take (140ms). Interactive focus uses a solid blue outline (2px) with an offset (4px). Import and loading spinners rotate over (1s); reduced-motion preference removes animations and transitions.

### Inputs and filters

Charcoal fields use clearly visible grey borders and gently curved corners. The username field reserves room for its clear control. Search has a leading icon, while native select controls handle imported player, import count, speed, and result. Keep visible labels or accessible names on all fields.

### Library rows and result markers

Each semantic list item contains a Win/Loss/Draw badge, opponent, rating, played color, time control, date, and an explicit Analyze navigation link. Rows are not whole-row buttons. Analyze has a quiet outline, dark blue hover fill, and an accessible name identifying the opponent and date. Long names wrap. On mobile, metadata rearranges beneath the opponent and action without horizontal scrolling.

### Replay navigation and Coach

Flip, first, previous turn, play/pause, next turn, and final controls sit below the board. Replay stops at the imported player's decision points, determined from the FEN side to move. A normal forward/back step briefly shows the intervening board for (100ms), then settles two half-moves away. Black's first forward step from the standard starting position advances only one half-move. Starting and final positions remain reachable for either colour. Board orientation does not change which player's turns are followed.

The slider selects these same decision points while the caption and counter retain the actual PGN half-move. Older bookmarks on an opponent's turn restore to the preceding player decision. Coach content and the announced position remain at the previous settled position during the brief board preview, and Run coach is disabled until it finishes. Rapid clicks advance from the pending destination; obsolete transition timers cannot overwrite newer input. Autoplay rests for (850ms) at each decision, then follows the same step sequence. Manual navigation pauses it. Pausing during a preview completes that pair before resting. Reduced-motion preference skips the intermediate board. A short keyboard hint identifies the player colour being followed.

The Coach response is one spacious outlined card without tabs. The toolbar sits directly above it with Coach, an info icon for saved response details, the model selector, and Run coach. Idle saved-status text and the redundant Coach response label are omitted; active requests and failures still show status messages. The card starts near the top of the board.

Understand the position has a small decision tag on the same heading row: Flexible uses muted blue, Clear preference amber, and Critical coral. The explanation appears in a tooltip on hover or keyboard focus. Terminal, single-move, and undefined mate-score comparisons use neutral tags. Classification comes from saved Stockfish evidence, never the model's old character label.

The thesis and needs paragraphs lead into one Moves list. Each row places SAN and optional Player move and quality indicators on the left, with its color-coded evaluation and board-preview icon aligned on the right. Its explanation appears immediately below. Positive side-to-move scores use green, negative scores muted red, and near-equal or bounded scores slate; tooltip and accessible labels identify perspective and meaning. Each move keeps its own score. Missing engine evidence stays blank. The played move appears once: a matching recommendation gains a blue Player move badge and dark blue row fill without a left stripe; an unlisted played move becomes the final row in the same list. Player severity labels are Good, Inaccuracy, Mistake, Blunder, or Quality uncertain. Good uses green, Inaccuracy amber, and Mistake/Blunder muted red with stronger weight for Blunder. The label tooltip explains the logistic winning-chance loss or mate transition. Severity remains separate from the blue identity marker and the unchanged position decision tag. A sound matching move reuses its candidate reason. Additional move feedback and any stronger-candidate link stay within the played row. The stored candidate pool and ordering do not change.

The selected row adds a blue (1px) outline and dark blue fill; keyboard focus remains a distinct (2px) outline. Selecting a row pauses autoplay and previews its arrow without playing the move. Recommendations retain their instructional squares; a separately listed player move highlights its origin and destination. Clear, navigation, new responses, and transient replay states prevent stale annotations. The board layout and controls retain their established styling. Older teaching and Markdown remain readable; missing combined feedback invites a rerun. No second-node essay is displayed.

The card uses (24px) padding, (16px) body text, 1.65 line height, and (17px) headings. Consecutive sections have (24px) top margin, (20px) top padding, and a fine divider. Move rows use (14px 12px) padding and (14px) explanations, with fine horizontal rules. At mobile widths the card padding becomes (18px), then (14px) below (370px); heading tags and move labels wrap naturally, and coarse-pointer comparison links remain at least (44px) tall. Repeated engine-source text and Show on board labels are replaced by one compact hint and row icons. Raw HTML and embedded Markdown images remain excluded.

The dropdown offers GPT-6 Astra and GPT-6.1 Terra, defaults to Astra, remembers the selection, and is disabled during a run. Both models use the same single-node, single-call flow. The info icon reveals the saved model, position, and timestamp on hover or focus. Changing model applies to the next run. Reruns retain the prior answer until success; failures appear inline. The editable Your question field remains below the card with a per-game local draft that is never submitted.


Keyboard arrows, Home, End, and Space support replay without intercepting typing in fields or interaction inside the Coach content. Factor summaries retain native Enter/Space activation and visible keyboard focus. Focused buttons keep their native Space activation.

Markdown blockquotes use a neutral (2px) quotation rule. This is an intentional exception to the detector's side-accent warning: it marks quoted prose, not a card or status callout.

### Board and player bars

Locally bundled Classic PNG pieces occupy each cell of an eight-by-eight CSS grid. Each square samples its corresponding tile from the full Icy Sea texture using an 800% background size. All twelve piece images and the texture are in `frontend/public/assets/chess/`; `SOURCES.json` records provenance. The header knight remains the original SVG.

Coordinates remain at the board's left and bottom edges after flipping. They use the opposite square color and scale with board width, matching the supplied reference. Their lower contrast is an intentional reference-matching exception confined to board coordinates; the existing accessible position summary is retained. Player bars follow orientation and identify the user's side; the caption announces position changes.

### Status and empty states

Loading and import feedback combine short text with a small icon. Failures use an error surface or a plainly labeled retry action. The initial screen shows only import and game selection; empty libraries have a text invitation to import, with no decorative board. Replay keeps Back to games available during loading and errors. The library's empty and filtered-empty states explain what is missing and provide an applicable next action.

## Do's and Don'ts

### Do:
- **Do** preserve the approved charcoal workspace, blue-grey board, and compact library.
- **Do** keep the settled board, slider, caption, and coaching synchronized to the actual PGN half-move; only the board previews the intervening position during a turn transition.
- **Do** use text alongside result and status colors.
- **Do** preserve visible keyboard focus and the implemented reduced-motion behavior.
- **Do** retain the locally bundled DM Sans, reference-matched board assets, and original header icon.

### Don't:
- **Don't** imply affiliation with Chess.com; keep the reference-matched artwork's source and ownership documented.
- **Don't** add decorative shadows or floating cards to the existing flat workspace.
- **Don't** let selection hide the distinction between last move and check.
- **Don't** replace a truthful empty library with invented game records.
