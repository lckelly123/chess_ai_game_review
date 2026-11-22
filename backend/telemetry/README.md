# Telemetry comparison

This display-only module classifies the existing Stockfish evidence when a coach
HTTP response is serialized, including saved reviews returned in game detail.
It does not run an engine or model, modify stored reviews, or feed labels into
coaching, severity, candidate selection, or Lessons.

`motifs.py` is an unmodified snapshot of
[PulfordJ/chess-telemetry](https://github.com/PulfordJ/chess-telemetry/blob/186ad9c61b770daf9c1778600a6a443be4ce3366/src/chess_telemetry/motifs.py)
at revision `186ad9c61b770daf9c1778600a6a443be4ce3366`. Its original attribution
and upstream ownership remain applicable; no additional license is asserted.

`classification.py` adapts the rank-1 and played-move root searches. It removes
the played move from the punishment PV, changes the post-move score to the
opponent's perspective (including mate distance and terminal results), and uses
upstream's phase rule, 1000 cp clamp, and default 200 cp motif threshold. It calls
the motif classifier directly; mate tags precede that threshold, as in upstream
`motifs.classify`. It does not import telemetry's separate game-level error
eligibility or severity policy. The source revision accompanies every result.
One adapter guard suppresses a false missed-mate label when the played move
actually checkmates: upstream's kept-mate check overlooks terminal `mate=0`.

This compares telemetry's rules on this application's engine evidence, not a
rerun of telemetry's independent position searches. The detector checks the
first best move and first opponent reply, prioritizes allowed over missed
tactics, and returns one original motif. Labels remain independent of the LLM's
taxonomy. `other` and `endgame_technique` are upstream fallbacks, not proof of a
specific positional cause. Missing/illegal PVs, absent moves, bounded scores,
inconsistent depths, and contradictory rankings report unavailable rather than
claiming no tactic. Below-threshold results are also identified separately.
