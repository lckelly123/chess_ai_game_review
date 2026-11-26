# Tactic classification (disabled)

The Lichess motif classification is disabled in game analysis, manual coaching,
and practice. The UI does not display its footer, including findings in older
saved reviews. The detector source and its tests are retained for reference;
no application path calls them or starts their extra Stockfish searches.
Existing saved data is preserved. Coach classifications and Lessons are separate
and remain enabled.

## Retained detector behavior

This module replaced the removed chess-telemetry comparison with a limited set of
Lichess puzzle detectors: fork, hanging piece, skewer, discovered attack/check,
absolute pin, and double check. It is independent of the coach's labels and
Lessons taxonomy. It does not change severity, approved candidates, or scores.

The existing shared player-move grader gates classification: only inaccuracies,
mistakes, and blunders are inspected. Good moves are not applicable; unreliable
root evidence is insufficient. A best-move continuation is inspected for the
player's missed motifs. The played-move continuation uses the played move as
Lichess's setup move and inspects the opponent's motifs. Both directions and all
matching motifs are retained; tags are heuristic evidence, not causal proofs.
No match is never automatically labelled positional.

Each line is limited to 16 half-moves from the actor's turn. Short, nonterminal
lines can receive one Stockfish leaf search each, capped at 200,000 nodes and
the smaller of two seconds or the configured search time. There are at most two
extra searches per eligible review. Terminal lines need no extension. Root
scores/PVs remain untouched. Invalid/missing root PVs are rejected. Extension
failures preserve valid prefixes and are explicitly marked as partial evidence.
Short lines with observed motifs retain those findings; short lines without a
match remain insufficient rather than claiming no tactic.

Previously, `analyze_played_move` ran this work during game analysis or manual
coaching and persisted the result as `stockfish.tactic_classification` through
the existing JSONB paths. That integration and its UI footer have been removed.
The comparison data remains excluded from the coach prompt.

## Upstream source

`lichess/` contains the Lichess puzzler tagger files at revision
`8e24b6d5e2b9618e41581a327926e4ac67c610a2`:
https://github.com/ornicar/lichess-puzzler/tree/8e24b6d5e2b9618e41581a327926e4ac67c610a2/tagger

The source is licensed under AGPL-3.0; its licence is retained in
`lichess/LICENSE`. This is distinct from the CC0 puzzle dataset.

Local changes to `cook.py`: package-relative imports; remove global logging setup; inspect a fork on the last
available actor move (a bounded PV need not end at a puzzle payoff); allow a
missing preceding setup move when classifying a standalone best-move position.
The adapter supplies that actual root node, never an invented null move. Only
the listed detectors are called; the upstream puzzle-goal, length, sacrifice,
and other tags are not emitted. Lichess pin rules cover particular uses of pins
to the king, and its hanging-piece rule is narrower than arbitrary profitable
captures. These limitations are intentional and must not be silently mapped
into broader claims.
