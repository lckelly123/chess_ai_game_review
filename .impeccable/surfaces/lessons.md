# Lessons

Mode: Operate. Route: `#lessons`.

The user's request is a precise addition to the existing app: a Lessons tab beside the game library, showing the severity breakdown within tactical and positional subcategories. Build directly in the established charcoal, DM Sans system; no new visual identity or concept selection is needed.

## Direction contract

- Purpose: compare inaccuracies, mistakes, and blunders across saved lesson categories for the selected player.
- Composition: persistent top navigation; Lessons heading and player/refresh controls; a compact sample-size summary; one grouped data table with category totals and an overall total.
- Data: count a pre-move decision once per game, use the latest matching saved coach label, exclude Good and Uncertain, and retain unclassified errors. Only current saved game analyses are included. Opening this page performs no engine searches or model calls.
- Identity: inherit DESIGN.md colors, DM Sans, existing field and focus styles, and 12px panel corners. Severity colors follow the replay legend. The table supplies the visual hierarchy; no decorative charts or metric cards.
- Interaction: real navigation links with current-page state, profile selection, refresh, retry, and an empty-state link to the library. Back/forward navigation and existing replay routes continue to work.
- Responsive: both tabs remain available on mobile, with a second header row. The table fits a narrow screen; Inaccuracy may shorten to Inacc. with its full accessible label. Subcategory names can wrap.
- Quality bar: counts reconcile across rows, categories, and severity columns; coverage states how much of the library was analyzed; zeros remain readable; no invented category assignments or fake data; no horizontal page overflow; loading/error/empty states are explicit.

No approved image comp: this is a code-led extension of a precisely specified existing interface.

Classification update: tactical groups are Missed tactics and Allowed tactics, each with hanging piece, fork, pin/skewer, and discovered attack. Positional rows name the best engine move’s piece, not the player’s moved piece. No-subcategory rows are retired; unsupported and earlier-version labels remain Unclassified. A notice above the table explains when existing reviews need updating and links to the library, without starting generation.
