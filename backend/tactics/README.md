# Tactic classification

This replaces the removed chess-telemetry comparison with a limited set of
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

`analyze_played_move` performs this work during initial game analysis or a manual
coach run. The result is persisted as `stockfish.tactic_classification` through
the existing JSONB paths. Opening/replaying a game makes no engine calls. Existing
records without this field display "Not yet analysed"; a new manual review
creates a new saved result. Nothing automatically rewrites historical reviews
or starts paid coaching. The comparison data is excluded from the coach prompt.
Live practice opts out with `include_tactics=False`, retaining only the shared
move grader and its existing root search. The footer remains hidden with the
rest of the review until the player reveals it after practice.

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
