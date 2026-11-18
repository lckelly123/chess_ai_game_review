---
name: Chess study
description: A quiet light workspace for revisiting your games, one position at a time.
colors:
  primary: "#315c78"
  primary-hover: "#234961"
  focus: "#426f90"
  workspace: "#f5f7f8"
  surface: "#ffffff"
  ink: "#243746"
  muted: "#5c6e7c"
  line: "#dce3e8"
  field-border: "#cbd6df"
  selected-row: "#eaf0f5"
  stripe: "#edf1f4"
  board-light: "#d6e4e9"
  board-dark: "#7399ad"
  last-move-overlay: "#d4d57088"
  check: "#d3978cb0"
  win-surface: "#e7f0e9"
  win-ink: "#3c6848"
  loss-surface: "#f7eae6"
  loss-ink: "#95523f"
  draw-surface: "#edf0f3"
  draw-ink: "#586b7b"
  error-surface: "#fbefec"
  error-ink: "#934e40"
typography:
  display:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "38px"
    fontWeight: 500
    lineHeight: 1.15
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "27px"
    fontWeight: 500
    letterSpacing: "-0.02em"
  game-title:
    fontFamily: "'DM Sans Variable', sans-serif"
    fontSize: "24px"
    fontWeight: 600
    letterSpacing: "-0.03em"
  title:
    fontFamily: "'DM Sans Variable', sans-serif"
    fontSize: "15px"
    fontWeight: 600
  body:
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
  control: "5px"
  field: "6px"
spacing:
  tight: "4px"
  inline: "8px"
  compact: "12px"
  standard: "16px"
  inset: "22px"
  workspace: "24px"
  replay-gap: "28px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    typography: "{typography.label}"
    rounded: "{rounded.field}"
    padding: "9px 10px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "9px 16px"
  button-text:
    textColor: "{colors.primary}"
    typography: "{typography.label}"
    padding: "0px"
  button-icon:
    rounded: "{rounded.control}"
    width: "36px"
    height: "36px"
  button-play:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    width: "38px"
    height: "36px"
  input-username:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    height: "43px"
    padding: "0px 32px 0px 12px"
  game-row:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    padding: "14px 20px"
  move-selected:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.move}"
    padding: "8px"
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

A quiet light workspace gives the chess position the strongest visual presence. Blue-grey squares, dark ink text, and a compact library support patient review. Newsreader adds a restrained editorial voice to invitations; DM Sans carries the working interface.

This records the implemented import and replay UI. The established direction is light surfaces, clear selection, and modest controls. The board artwork follows the user's November 15, 2026 reference; the surrounding workspace retains its independent identity.

**Key Characteristics:**
- Light, flat surfaces separated by fine rules.
- An Icy Sea textured board with Classic black-and-white pieces, matching the supplied reference.
- Compact game rows and precise move selection.
- Serif invitations paired with sans-serif working controls.

## Colors

The palette is cool and muted, with semantic colors reserved for game and request state. Frontmatter contains the normative values; the sidecar's generated tonal ramps are preview metadata, not additional implementation tokens.

### Primary

Deep slate blue identifies the import action, replay play button, text actions, and current move. A deeper hover shade supports the import action; focus blue makes keyboard position visible.

### Neutral

Cool workspace grey surrounds white library and header surfaces. Ink carries content; muted slate carries supporting text. Pale rules divide sections, field borders define inputs, and a light blue hover fill identifies the Analyze action. White text areas define the Coach response and question fields.

### Semantic and board colors

The locally bundled Icy Sea image supplies the board's textured light and blue squares; board color tokens are fallback colors. Translucent olive marks the last move and muted coral marks check, preserving the texture beneath each highlight. Wins use sage, losses use clay, and draws use slate, always accompanied by text. Request errors have their own pale clay surface and readable error ink.

**The Position State Rule.** Keep the position caption, last-move squares, and check distinguishable; each communicates a different part of the replay state.

## Typography

Newsreader (Georgia fallback) supplies the library page title and the small italic vs separator. DM Sans Variable supplies controls, names, metadata, and notation. Both fonts are bundled locally.

The library title is (38px), saved-games heading (19px), opponent names (14px), and working controls (12-14px). At narrow widths the library title becomes (32px) and game titles (23px). Counts, dates, and move numbers use tabular numerals where applicable.

## Layout and navigation

The app has two separate screens. The root URL opens the game library without a board. The library is centered at a maximum outer width of (1120px), with (38px 36px 24px) padding. A (76px) white header sits above it. A short title leads into one compact import form, then saved-player selection, search, filters, and a scrollable list. Desktop rows align result, opponent, time control, date, and Analyze in columns.

Analyze opens a hash route containing the game ID and player. The dedicated replay screen has a maximum outer width of (1800px), a Back to games link, game heading, board, and Coach panel. The board caps at (620px). Board and Coach share the width in a .95:2 ratio with a (28px) gap. Inside Coach, one outlined response panel spans the available width. Position teaching, candidates, and move feedback share one card. The panel grows with its content and the page scrolls naturally. Browser navigation and direct replay links work. Returning within the session restores filters, list/page scrolling, and focus to the originating Analyze link. Replay position remains saved per game.

- At (1200px) and below, the board remains beside the single Coach response panel.
- At (960px) and below, page side padding becomes (24px), game columns tighten, and the replay gap becomes (24px).
- At (900px) and below, Coach moves below the centered board; the combined response remains one panel.
- At (700px) and below, the header becomes (64px), library side padding (18px), and import controls wrap under the username. Filters sit below search. Game rows place their Analyze link on the right with date beneath it. The list caps at (520px).
- At (700px) and below, replay uses one column. Replay side padding is (16px); the response body uses (14px) padding. Candidate rows and stronger-move links retain touch targets at least (44px) tall.
- At (370px) and below, spacing and replay controls tighten. The body supports a minimum width of (320px).

## Elevation & Depth

The implementation has no shadows. White surfaces, the grey workspace, thin borders, white text areas, and action hover fills establish hierarchy. Interactive feedback is a color change, not movement or elevation.

## Shapes

The board has square outer corners to match the reference. Player tokens retain (3px) corners; notation selection and result labels use the move radius; icon controls and result marks use the control radius; inputs, import actions, and status blocks use the field radius; game rows remain flat with horizontal dividers. Section boundaries and field outlines use fine (1px) borders.

## Components

### Buttons and focus

Primary import actions use slate blue with white labels and a trailing arrow; replay play/pause uses the same emphasis in a compact icon control. Secondary retry actions are white with an outline. Text actions have no container and underline on hover. Icon controls are transparent until hovered. Disabled buttons use reduced opacity (.42) and a default cursor.

Button color transitions take (140ms). Interactive focus uses a solid blue outline (2px) with an offset (4px). Import and loading spinners rotate over (1s); reduced-motion preference removes animations and transitions.

### Inputs and filters

White fields use muted borders and gently curved corners. The username field reserves room for its clear control. Search has a leading icon, while native select controls handle imported player, import count, speed, and result. Keep visible labels or accessible names on all fields.

### Library rows and result markers

Each semantic list item contains a Win/Loss/Draw badge, opponent, rating, played color, time control, date, and an explicit Analyze navigation link. Rows are not whole-row buttons. Analyze has a quiet outline, pale blue hover fill, and an accessible name identifying the opponent and date. Long names wrap. On mobile, metadata rearranges beneath the opponent and action without horizontal scrolling.

### Replay navigation and Coach

Flip, first, previous turn, play/pause, next turn, and final controls sit below the board. Replay stops at the imported player's decision points, determined from the FEN side to move. A normal forward/back step briefly shows the intervening board for (100ms), then settles two half-moves away. Black's first forward step from the standard starting position advances only one half-move. Starting and final positions remain reachable for either colour. Board orientation does not change which player's turns are followed.

The slider selects these same decision points while the caption and counter retain the actual PGN half-move. Older bookmarks on an opponent's turn restore to the preceding player decision. Coach content and the announced position remain at the previous settled position during the brief board preview, and Run coach is disabled until it finishes. Rapid clicks advance from the pending destination; obsolete transition timers cannot overwrite newer input. Autoplay rests for (850ms) at each decision, then follows the same step sequence. Manual navigation pauses it. Pausing during a preview completes that pair before resting. Reduced-motion preference skips the intermediate board. A short keyboard hint identifies the player colour being followed.

The Coach response is one compact outlined card without tabs. The toolbar sits directly above it with Coach, an info icon for saved response details, the model selector, and Run coach. Idle saved-status text and the redundant Coach response label are omitted; active requests and failures still show status messages. The card starts near the top of the board.

Understand the position has a small decision tag on the same heading row: Flexible uses muted blue, Clear preference amber, and Critical coral. The explanation appears in a tooltip on hover or keyboard focus. Terminal, single-move, and undefined mate-score comparisons use neutral tags. Classification comes from saved Stockfish evidence, never the model's old character label.

The thesis and needs paragraphs lead into one Moves list. Each compact row puts SAN, a color-coded evaluation, optional Player move and quality indicators, and a board-preview icon on one line, with its explanation immediately below. Positive side-to-move scores use green, negative scores muted red, and near-equal or bounded scores slate; tooltip and accessible labels identify perspective and meaning. Each move keeps its own score. Missing engine evidence stays blank. The played move appears once: a matching recommendation gains a blue Player move badge, pale blue row, and blue left border; an unlisted played move becomes the final row in the same list. Quality remains separate from the blue identity marker. A sound matching move reuses its candidate reason. Additional move feedback and any stronger-candidate link stay within the played row. The stored candidate pool and ordering do not change.

Selecting a row pauses autoplay and previews its arrow without playing the move. Recommendations retain their instructional squares; a separately listed player move highlights its origin and destination. Clear, navigation, new responses, and transient replay states prevent stale annotations. The board layout and controls retain their established styling. Older teaching and Markdown remain readable; missing combined feedback invites a rerun. No second-node essay is displayed.

The card uses (16px 18px) padding, (14px) body text, 1.5 line height, (16px) headings, and (16px) section gaps. Move rows use (10px) padding and (13px) explanations, with fine horizontal rules. At mobile widths the card padding becomes (14px), heading tags and move labels wrap naturally, and touch links remain at least (44px) tall. Repeated engine-source text and Show on board labels are replaced by one compact hint and row icons. Raw HTML and embedded Markdown images remain excluded.

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
- **Do** preserve the light workspace, blue-grey board, and compact library.
- **Do** keep the settled board, slider, caption, and coaching synchronized to the actual PGN half-move; only the board previews the intervening position during a turn transition.
- **Do** use text alongside result and status colors.
- **Do** preserve visible keyboard focus and the implemented reduced-motion behavior.
- **Do** retain the locally bundled typefaces, reference-matched board assets, and original header icon.

### Don't:
- **Don't** imply affiliation with Chess.com; keep the reference-matched artwork's source and ownership documented.
- **Don't** add decorative shadows or floating cards to the existing flat workspace.
- **Don't** let selection hide the distinction between last move and check.
- **Don't** replace a truthful empty library with invented game records.
