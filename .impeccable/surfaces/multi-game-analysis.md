# Multi-game analysis

Mode: Operate / Read. Route: `#lessons/multi-game`. Build path: code.
Primary target: `frontend/src/MultiGameAnalysis.tsx`. Related targets: `frontend/src/multiGameAnalysis.css`, `frontend/src/Lessons.tsx`.

This is a user-requested extension of Lessons within the existing design system. No new visual identity or comp is required.

## Direction contract

- THESIS: Turn the player's saved mistakes across games into a focused coaching report, with previous reports available on the same screen.
- OWN-WORLD: Inherit the pure-black canvas, DM Sans, soft white primary actions, muted blue links, fine dividers, and existing navigation.
- STORY: Open Multi-game analysis from Lessons, review the available sample, run the coach explicitly, then read the profile, patterns, thinking adjustments, and practice priorities. Select an earlier saved response to revisit it.
- FIRST VIEWPORT: Back to lessons, the page title and Run analysis action, refresh and sample counts, shared header account settings, then response history and the opening assessment. On mobile, the action takes the available width and the response selector stacks above the report.
- SIGNATURE INTERACTION: Starting a background analysis preserves the prior report; completion selects the newest saved response. Navigation away and returning restores durable progress.
- CONTENT: All production counts and coaching come from saved backend results. Browser QA uses an explicitly labeled synthetic preview with no paid calls.
- QUALITY BAR: Run only on explicit click; disable duplicates; explain missing data, loading, and failures; preserve old responses; readable prose; keyboard-native controls; no horizontal overflow at 320px and above.
