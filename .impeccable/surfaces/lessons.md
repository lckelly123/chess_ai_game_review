# Lessons

Status: Retired; superseded by [Analytics](analytics.md). The former `#lessons`
and `#lessons/multi-game` routes now resolve to `#analytics`. This brief retains
the historical Lessons direction; it does not describe the current interface.

Mode: Operate. Route: `#lessons`. Direction: `lessons-explorer-2026-11-21`.

The user requested a layout like the supplied summary-card and topic-list reference, while retaining the current color palette. This replaces the grouped table within the established app; no new visual identity or concept selection is needed. Build path: code. The reference is structural inspiration, not an exact reproduction.

## Direction contract

- THESIS: Turn saved lesson counts into a focused category explorer, with totals first and topic detail on demand.
- OWN-WORLD: Inherit pure-black canvas and panels, DM Sans, soft white text, muted sky-blue selection, amber/orange/coral severity colors, fine borders, and 12px panel corners.
- STORY: Compare Positional and Tactical totals, select a category, narrow severity, and expand a topic to inspect its full breakdown. Unclassified errors remain reachable.
- FIRST VIEWPORT: Heading, Multi-game analysis link and refresh control, shared header account settings, sample coverage, two equal summary buttons with segmented severity bars, a quiet Unclassified row, then tactical subgroup and severity filters with proportional topic rows. Cards stack on narrow mobile screens.
- FORM: User-provided reference `codex-clipboard-9742a2b8-6e99-4cdd-b549-ea73f17ff36d.png`, code-led, no generated comp. Signature interaction: filtering recomputes matching counts, ordering, and bar proportions without new network work.

## Data and interaction

Use the unchanged `/api/lessons` response. Combine Missed tactics and Allowed tactics only for the Tactical overview; keep the two separate in exploration. Positional topics identify the best engine move's piece. Each game decision is counted once, Good and Uncertain are excluded, and Unclassified is never folded into another category. Opening Lessons performs no engine or model work.

Cards and filters are native buttons with pressed states. Topic disclosures are native details/summary with full severity counts and a proportion of the current matching set. They do not promise individual move lists, which this endpoint does not return. Use the shared header account dialog for player selection. Retain local refresh, retry, coverage, stale-review notices, empty states, and navigation.

## Quality bar

Counts reconcile across group totals and filters; bars have text equivalents; selected and focused controls are distinguishable; no horizontal overflow at 320px or larger; each interaction has a meaningful outcome. Preserve the user's earlier replay simplifications and pure-black palette. No new images or invented production data.
