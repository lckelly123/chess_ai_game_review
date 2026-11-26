import asyncio
from copy import deepcopy
import json
from unittest.mock import Mock

import chess
import chess.engine
import httpx2
import pytest

from backend.coach.move_quality import analyze_played_move, prepare_position_evidence
from backend.coach.move_review import MoveReview
from backend.coach.player_move_quality import assess_player_move, with_player_move_quality
from backend.coach.position_classification import compare_candidate_moves
from backend.coach.stockfish import StockfishAnalysisError, StockfishSettings, StockfishUnavailableError
from backend.tests.position_fixtures import position_evidence
from backend.tests.test_position_classification import FakeEngine, info, install


FEN = "1q2kb1r/p1pn1ppp/3p4/4p3/4P3/5N1P/PPP2PP1/RNBQK2R w KQk - 0 12"
ROOTS = ["e1g1", "a2a3", "b1c3", "a2a4", "d1e2"]
PLAYED = "d1d5"


def original_position():
    evidence = position_evidence(FEN, preferred=ROOTS)
    for move, cp in zip(evidence["top_moves"], [999, 999, 995, 987, 978]):
        move.update(depth=18, wdl={"wins": 1000, "draws": 0, "losses": 0},
                    expected_score=1., probabilities={"win": 1., "draw": 0., "loss": 0.})
        move["score"]["cp"] = cp
    return prepare_position_evidence(evidence)


def single_search(monkeypatch, **changes):
    engine = Mock()
    engine.__enter__ = Mock(return_value=engine)
    engine.__exit__ = Mock(return_value=False)
    engine.id = {"name": "Single search"}
    engine.options = {"UCI_ShowWDL": True}
    engine.analyse.return_value = {**info(PLAYED, 1001, (1000, 0, 0), 1, depth=18), **changes}
    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", lambda *args, **kwargs: engine)
    monkeypatch.setattr(StockfishSettings, "executable", lambda self: "test-stockfish")
    return engine


@pytest.mark.parametrize("player_first", [True, False])
def test_conflicting_search_regrades_and_reranks_the_whole_pool(monkeypatch, player_first):
    original = original_position()
    snapshot = deepcopy(original)
    single = single_search(monkeypatch)
    ordered = [PLAYED, *ROOTS] if player_first else [*ROOTS, PLAYED]
    scores = [1005, 1000, 995, 990, 985, 980] if player_first else [1000, 999, 995, 990, 985, 0]
    # The retry may reach a shallower depth, but every compared score must come
    # from that same completed batch, including a player who finishes sixth.
    shared = FakeEngine([info(uci, cp, (1000, 0, 0), rank, depth=16)
                         for rank, (uci, cp) in enumerate(zip(ordered, scores), 1)])
    install(monkeypatch, shared)
    settings = StockfishSettings(depth=25, time_limit=3, threads=1, hash_mb=16)
    result = analyze_played_move(MoveReview.from_fen(FEN, PLAYED), original, settings)

    assert single.analyse.call_args.args[1].depth == 18
    assert shared.request[0] == FEN and shared.request[1].depth == 18
    assert shared.request[1].time == 3
    assert shared.request[2] == {"multipv": 6, "root_moves": [chess.Move.from_uci(uci) for uci in [*ROOTS, PLAYED]]}
    assert [move["uci"] for move in result["top_moves"]] == ordered[:5]
    assert [move["score"]["cp"] for move in result["top_moves"]] == scores[:5]
    assert result["played_move"]["score"]["cp"] == scores[0 if player_first else -1]
    assert {move["depth"] for move in [*result["top_moves"], result["played_move"]]} == {16}
    assert result["played_move_in_top"] is player_first
    assert result["played_move"]["rank"] == (1 if player_first else 6)
    assert result["move_quality"]["status"] == ("good" if player_first else "blunder")
    assert result["move_quality"] == assess_player_move(result["top_moves"][0], result["played_move"])
    assert with_player_move_quality(result)["move_quality"] == result["move_quality"]
    position = result["position_evidence"]
    assert position["top_moves"] == result["top_moves"]
    assert position["position_outlook"]["score"] == result["top_moves"][0]["score"]
    assert position["permitted_candidate_uci"] == ordered[:3]
    assert position["top_moves"][1]["relative_quality"]["cp_loss_from_best"] == scores[0] - scores[1]
    assert position["sharpness"] == prepare_position_evidence(position)["sharpness"]
    assert original == snapshot
    assert shared.closed and shared.stream.stopped


@pytest.mark.parametrize("changes,expected", [
    ({"depth": 17}, "uncertain"),
    ({"upperbound": True}, "uncertain"),
    ({"score": chess.engine.PovScore(chess.engine.Cp(990), chess.WHITE)}, "good"),
])
def test_only_reliable_conflicts_trigger_shared_comparison(monkeypatch, changes, expected):
    single_search(monkeypatch, **changes)
    comparison = Mock(side_effect=AssertionError("No shared search needed"))
    monkeypatch.setattr("backend.coach.move_quality.compare_candidate_moves", comparison)
    result = analyze_played_move(MoveReview.from_fen(FEN, PLAYED), original_position())
    assert result["move_quality"]["status"] == expected
    assert "position_evidence" not in result
    comparison.assert_not_called()


def test_newly_found_mate_is_also_compared_together(monkeypatch):
    single_search(monkeypatch, score=chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE))
    shared = FakeEngine([
        info(PLAYED, None, (1000, 0, 0), 1, depth=18, score=chess.engine.Mate(4)),
        *[info(uci, 990 - rank, (1000, 0, 0), rank, depth=18) for rank, uci in enumerate(ROOTS, 2)],
    ])
    install(monkeypatch, shared)
    result = analyze_played_move(MoveReview.from_fen(FEN, PLAYED), original_position())
    assert result["top_moves"][0]["uci"] == PLAYED
    assert result["played_move"]["score"]["mate"] == 4
    assert result["move_quality"]["reason"] == "mate_retained"
    assert result["move_quality"]["status"] == "good"


@pytest.mark.parametrize("defect", ["missing", "wrong_root", "mixed_depth", "bound"])
def test_shared_comparison_rejects_incomplete_or_wrong_root_batches(monkeypatch, defect):
    roots = [*ROOTS, PLAYED]
    batch = [info(uci, 999 - rank, (1000, 0, 0), rank, depth=18) for rank, uci in enumerate(roots, 1)]
    if defect == "missing":
        batch.pop()
    elif defect == "wrong_root":
        batch[-1]["pv"] = [chess.Move.from_uci("h1f1")]
    elif defect == "mixed_depth":
        batch[-1]["depth"] = 17
    else:
        batch[-1]["upperbound"] = True
    shared = FakeEngine(batch)
    install(monkeypatch, shared)
    single_search(monkeypatch)
    with pytest.raises(StockfishAnalysisError, match="complete, consistent"):
        analyze_played_move(MoveReview.from_fen(FEN, PLAYED), original_position())
    assert shared.closed


def test_shared_comparison_keeps_last_complete_batch_and_black_perspective(monkeypatch):
    board = chess.Board(FEN).mirror()
    roots = [chess.Move(chess.square_mirror(chess.Move.from_uci(uci).from_square),
                        chess.square_mirror(chess.Move.from_uci(uci).to_square)).uci() for uci in [PLAYED, *ROOTS]]
    complete = [info(uci, 1000 - rank, (1000, 0, 0), rank, color=chess.BLACK, depth=16)
                for rank, uci in enumerate(roots, 1)]
    shared = FakeEngine([*complete, info(roots[1], 1100, (1000, 0, 0), 1, color=chess.BLACK, depth=17)])
    install(monkeypatch, shared)
    _, compared = compare_candidate_moves(board.fen(), roots, StockfishSettings(depth=18))
    assert [move["uci"] for move in compared] == roots
    assert [move["score"]["cp"] for move in compared] == list(range(999, 993, -1))
    assert {move["depth"] for move in compared} == {16}


def test_game_analysis_retains_verified_position_instead_of_original(monkeypatch):
    from backend.game_analysis import analyze_game_move

    original = original_position()
    verified = {**deepcopy(original), "engine": "Verified comparison"}
    monkeypatch.setattr("backend.game_analysis.analyze_position", lambda _: original)
    monkeypatch.setattr("backend.game_analysis.analyze_played_move", lambda *_: {
        "position_evidence": verified, "top_moves": verified["top_moves"], "played_move": {"uci": PLAYED},
    })
    result = analyze_game_move(MoveReview.from_fen(FEN, PLAYED))
    assert result["position_evidence"] == verified


def test_coach_preview_uses_verified_candidates_and_scores(monkeypatch):
    from backend.coach.responses import build_request

    original = original_position()
    verified = position_evidence(FEN, preferred=[PLAYED, *ROOTS])
    played = {**verified["top_moves"][0], "quality": {"status": "good"}}
    move_result = {"position_evidence": verified, "played_move": played, "move_quality": played["quality"]}
    snapshot = deepcopy(move_result)
    monkeypatch.setattr("backend.coach.responses.analyze_played_move", lambda *_: move_result)
    message = build_request(FEN, evidence=original, played_move=PLAYED)["input"][1]["content"]
    assert "d1d5 | 100 cp" in message and "e1g1 | 90 cp" in message
    assert "999 cp" not in message and "Severity: good" in message
    assert move_result == snapshot


def test_coach_generation_saves_the_same_verified_evidence_as_its_prompt():
    from backend.coach.responses import ResponsesCoach
    from backend.tests.test_coach import completed_response
    from backend.tests.test_coach_graph import mock_client

    original = original_position()
    verified = position_evidence(FEN, preferred=[PLAYED, *ROOTS])
    played = verified["top_moves"][0]
    move_result = {"fen": FEN, "perspective": "White", "position_evidence": verified,
                   "top_moves": verified["top_moves"], "played_move": played,
                   "move_quality": played["quality"]}
    snapshot = deepcopy(move_result)
    requests = []

    def upstream(request):
        message = json.loads(request.content)["input"][1]["content"]
        requests.append(message)
        assert "d1d5 | 100 cp" in message and "e1g1 | 90 cp" in message
        assert "999 cp" not in message
        return httpx2.Response(200, json=completed_response(request=request))

    async def run():
        async with mock_client(upstream) as client:
            coach = ResponsesCoach(client, position_engine=lambda _: original, engine=lambda *_: move_result)
            return await coach.analyze(FEN, played_move=PLAYED)

    result = asyncio.run(run())
    assert len(requests) == 1
    assert result.engine_evidence == verified
    assert result.stockfish["top_moves"] == verified["top_moves"]
    assert "position_evidence" not in result.stockfish
    assert [move["uci"] for move in result.structured["candidate_moves"]] == verified["permitted_candidate_uci"]
    assert move_result == snapshot


def test_real_stockfish_resolves_saved_qd5_conflict(monkeypatch):
    settings = StockfishSettings(depth=18, time_limit=2, threads=1, hash_mb=16)
    try:
        executable = settings.executable()
    except StockfishUnavailableError:
        pytest.skip("Install Stockfish for the native comparison smoke test.")
    # Reproduce the saved 999 / 1001 conflict deterministically; the shared
    # verification itself uses real Stockfish and all six legal roots.
    single_search(monkeypatch)
    monkeypatch.setattr(StockfishSettings, "executable", lambda self: executable)
    result = analyze_played_move(MoveReview.from_fen(FEN, PLAYED), original_position(), settings)
    assert result["move_quality"]["status"] != "uncertain"
    assert len(result["top_moves"]) == 5
    assert {move["uci"] for move in result["top_moves"]} <= {*ROOTS, PLAYED}
    assert len({move["depth"] for move in [*result["top_moves"], result["played_move"]]}) == 1
    assert result["position_evidence"]["top_moves"] == result["top_moves"]
    assert result["move_quality"] == assess_player_move(result["top_moves"][0], result["played_move"])
