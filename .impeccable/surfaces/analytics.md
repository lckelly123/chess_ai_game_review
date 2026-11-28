# Analytics

Mode: Operate. Route: `#analytics`. Build path: code.

Replaces the Lessons tab with the user's seven specified graphs. Inherit the
established pure-black canvas, DM Sans, soft white text, muted sky blue, and fine
rules. No new visual identity or generated assets. Legacy Lessons bookmarks
resolve to Analytics; saved coaching and multi-game report data remain intact.

## Direction contract

- Heading and manual refresh, then speed and exact time-control selectors.
- Tactical: grouped missed/allowed counts across four motifs.
- Positional: four contexts, a 6 × 6 actual-piece/engine-piece heatmap, and four
  context series across three displayed outlook groups.
- Game Stats: error rates by phase, five sharpness levels, and five outlook bands.
- Use flat sections and plot gridlines. On desktop pair compatible graphs; on
  mobile stack them. Keep every label legible and data available as text.
- Heatmap rows are actual pieces; columns are engine-preferred pieces. Named
  cells retain numeric values and light text on blue shading.
- SVG plots have textual descriptions and expandable data tables. Native
  filters, refresh and retry controls work with keyboard focus.

## Data contract

Seven persisted player/time-control summaries feed the charts. Selected controls
sum counts before division. Errors are Inaccuracy, Mistake and Blunder; uncertain
grades are excluded. Coach classifications are required for the first four
graphs. All outlooks are player-relative and pre-move: Losing < −300 cp, Worse
−300 to < −50, Equal −50 through +50, Better > +50 through +300, Winning > +300.
Forced mates map to Losing/Winning. Context/outlook combines Worse into Losing
and Better into Winning only in presentation. Zero eligible moves show no data.

Page load, manual refresh, import, saved analysis/coaching and reset update
summaries without engine/model calls. Poll saved summaries while the page is
visible. Loading, no-account, no-analysis and error/retry states preserve the
distinction between zero errors and missing analysis.

## Quality bar

All seven plots and the two filters are present. Test at 1440, 390 and 320 pixels;
no page-level horizontal overflow. Counts and sample denominators remain
inspectable. Synthetic review data stays in browser test fixtures only.
