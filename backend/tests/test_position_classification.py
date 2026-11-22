import asyncio
import json
import os

import chess
import chess.engine
import pytest

from backend.coach.position import InvalidPositionError
from backend.coach.position_classification import analyze_position, classify_position
from backend.coach.stockfish import (
    StockfishAnalysisError, StockfishSettings, StockfishTimeoutError,
    StockfishUnavailableError,
)


def info(uci, cp, wdl, rank, *, color=chess.WHITE, depth=12, score=None, **extra):
    return {
        "pv": [chess.Move.from_uci(uci)], "multipv": rank, "depth": depth,
        "score": chess.engine.PovScore(score if score is not None else chess.engine.Cp(cp), color),
        "wdl": chess.engine.PovWdl(chess.engine.Wdl(*wdl), color), **extra,
    }


def pair(cp_gap=35, best_wdl=(600, 0, 400), second_wdl=(550, 0, 450)):
    return [info("e2e4", 30 + cp_gap, best_wdl, 1),
            *[info(uci, 30, second_wdl, rank) for rank, uci in enumerate(["d2d4", "g1f3", "c2c4", "b1c3"], 2)]]


class FakeAnalysis:
    def __init__(self, infos, *, failure=None, stall=False):
        self.infos, self.failure, self.stall = infos, failure, stall
        self.stopped = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stopped = True

    async def __aiter__(self):
        if self.failure:
            raise self.failure
        if self.stall:
            await asyncio.sleep(100)
        for item in self.infos:
            yield item


class FakeEngine:
    id = {"name": "Stockfish test"}

    def __init__(self, infos, **kwargs):
        self.options = {"UCI_ShowWDL": object()}
        self.stream = FakeAnalysis(infos, **kwargs)
        self.closed = False

    async def configure(self, options):
        self.configured = options

    async def analysis(self, board, limit, **kwargs):
        self.request = (board.fen(en_passant="fen"), limit, kwargs)
        return self.stream

    def close(self):
        self.closed = True


def install(monkeypatch, engine):
    monkeypatch.setattr(StockfishSettings, "executable", lambda self: "test-stockfish")

    async def start(path):
        assert path == "test-stockfish"
        return engine, engine  # transport and UCI protocol

    monkeypatch.setattr(chess.engine, "popen_uci", start)


@pytest.mark.parametrize("cp_gap,best_wins,second_wins,expected", [
    (0, 500, 500, "Forgiving"),
    (35, 600, 550, "Flexible"),
    (36, 600, 550, "Flexible"),
    (35, 601, 550, "Flexible"),
    (10, 799, 600, "Forgiving"),
    (10, 800, 600, "Forgiving"),  # WDL does not set the position tag.
    (500, 1000, 0, "Critical"),
    (100, 1000, 1000, "Selective"),
    (200, 1000, 1000, "Demanding"),
])
def test_exact_classification_thresholds(monkeypatch, cp_gap, best_wins, second_wins, expected):
    engine = FakeEngine(pair(cp_gap, (best_wins, 0, 1000 - best_wins), (second_wins, 0, 1000 - second_wins)))
    install(monkeypatch, engine)
    result = classify_position(chess.STARTING_FEN)
    assert result["classification"] == expected
    assert result["delta_cp"] == cp_gap
    assert result["delta_e_pp"] == (best_wins - second_wins) / 10
    assert result["unclassified_reason"] is None
    assert engine.closed and engine.stream.stopped
    json.dumps(result, allow_nan=False)


def test_native_wdl_draws_configuration_and_evidence(monkeypatch):
    engine = FakeEngine(pair(best_wdl=(300, 600, 100), second_wdl=(200, 700, 100)))
    install(monkeypatch, engine)
    result = classify_position(chess.STARTING_FEN, StockfishSettings(depth=14, time_limit=3, threads=1, hash_mb=32))
    assert engine.configured == {"Threads": 1, "Hash": 32, "UCI_ShowWDL": True}
    fen, limit, options = engine.request
    assert fen == chess.STARTING_FEN and options == {"multipv": 5}
    assert limit.depth == 14 and limit.time == 3
    assert result["engine"] == "Stockfish test" and result["perspective"] == "White"
    assert result["top_moves"][0]["expected_score"] == .6
    assert result["top_moves"][1]["expected_score"] == .55
    assert result["top_moves"][0]["probabilities"] == {"win": .3, "draw": .6, "loss": .1}
    assert result["top_moves"][0]["san"] == "e4"
    assert result["delta_e_pp"] == 5 and result["classification"] == "Flexible"


def test_black_perspective_flips_both_cp_and_wdl(monkeypatch):
    board = chess.Board()
    board.push_uci("e2e4")
    engine = FakeEngine([
        info("e7e5", -65, (100, 600, 300), 1),
        info("c7c5", -30, (100, 700, 200), 2),
        info("g8f6", -30, (100, 700, 200), 3),
        info("e7e6", -30, (100, 700, 200), 4),
        info("d7d6", -30, (100, 700, 200), 5),
    ])
    install(monkeypatch, engine)
    result = classify_position(board.fen(en_passant="fen"))
    assert result["perspective"] == "Black"
    assert result["delta_cp"] == 35 and result["delta_e_pp"] == 5
    assert result["top_moves"][0]["wdl"] == {"wins": 300, "draws": 600, "losses": 100}
    assert result["top_moves"][0]["score"]["cp"] == 65
    assert result["classification"] == "Flexible"
    assert " e3 " in result["fen"]


def test_partial_latest_iteration_uses_last_complete_depth(monkeypatch):
    engine = FakeEngine([*pair(), info("g1f3", 400, (1000, 0, 0), 1, depth=13),
                         info("d2d4", 10, (500, 0, 500), 2, depth=13, upperbound=True)])
    install(monkeypatch, engine)
    result = classify_position(chess.STARTING_FEN)
    assert result["classification"] == "Flexible"
    assert [move["depth"] for move in result["top_moves"]] == [12] * 5
    assert result["top_moves"][0]["uci"] == "e2e4"


@pytest.mark.parametrize("finish_mixed_batch", [False, True])
def test_rank_changes_do_not_corrupt_saved_five_move_batch(monkeypatch, finish_mixed_batch):
    # The 55...Rh8 failure: a newer ranking moves Ra1 from fourth to third.
    # Its leaders have advanced a depth, while the remaining lines have not.
    fen = "r7/5k2/7P/6RK/6P1/8/8/8 b - - 2 55"
    roots = ["f7e6", "f7f6", "a8a6", "a8a1", "f7f8"]
    completed = [info(uci, -1010 - rank, (0, 0, 1000), rank, color=chess.BLACK, depth=14)
                 for rank, uci in enumerate(roots, 1)]
    mixed = [{**completed[0], "depth": 15}, {**completed[1], "depth": 15},
             {**completed[3], "multipv": 3}]
    if finish_mixed_batch:
        mixed += [{**completed[2], "multipv": 4}, completed[4]]
    engine = FakeEngine([*completed, *mixed])
    install(monkeypatch, engine)
    result = analyze_position(fen)
    assert [move["uci"] for move in result["top_moves"]] == roots
    assert [move["depth"] for move in result["top_moves"]] == [14] * 5
    assert result["delta_cp"] == 1 and result["delta_e_pp"] == 0
    assert result["classification"] == "Forgiving"


@pytest.mark.parametrize("change", ["partial", "missing_first", "mixed_depth", "duplicate", "reversed_cp",
                                   "reversed_wdl", "illegal_pv", "missing_wdl", "bound"])
def test_bad_later_batch_preserves_last_valid_snapshot(monkeypatch, change):
    completed = pair()
    later = [info("g1f3", 100, (700, 0, 300), 1), info("c2c4", 90, (690, 0, 310), 2)]
    later += [info(uci, 80, (680, 0, 320), rank) for rank, uci in enumerate(["e2e4", "d2d4", "b1c3"], 3)]
    if change == "partial":
        later.pop()
    elif change == "missing_first":
        later.pop(0)
    elif change == "mixed_depth":
        later[0]["depth"] = 13
    elif change == "duplicate":
        later[1]["pv"] = later[0]["pv"]
    elif change == "reversed_cp":
        later[1]["score"] = chess.engine.PovScore(chess.engine.Cp(200), chess.WHITE)
    elif change == "reversed_wdl":
        later[1]["wdl"] = chess.engine.PovWdl(chess.engine.Wdl(1000, 0, 0), chess.WHITE)
    elif change == "illegal_pv":
        later[0]["pv"] = [chess.Move.from_uci("e2e5")]
    elif change == "missing_wdl":
        del later[0]["wdl"]
    elif change == "bound":
        later[0]["lowerbound"] = True
    engine = FakeEngine([*completed, *later])
    install(monkeypatch, engine)
    result = classify_position(chess.STARTING_FEN)
    assert [move["uci"] for move in result["top_moves"]] == ["e2e4", "d2d4", "g1f3", "c2c4", "b1c3"]
    assert result["delta_cp"] == 35 and result["delta_e_pp"] == 5


@pytest.mark.parametrize("depth,expected", [(11, "e2e4"), (12, "g1f3"), (13, "g1f3")])
def test_latest_valid_batch_at_deepest_completed_depth_is_used(monkeypatch, depth, expected):
    engine = FakeEngine([*pair(), info("g1f3", 100, (700, 0, 300), 1, depth=depth),
                         info("c2c4", 90, (690, 0, 310), 2, depth=depth),
                         *[info(uci, 80, (680, 0, 320), rank, depth=depth) for rank, uci in enumerate(["e2e4", "d2d4", "b1c3"], 3)]])
    install(monkeypatch, engine)
    result = classify_position(chess.STARTING_FEN)
    assert result["top_moves"][0]["uci"] == expected
    assert {move["depth"] for move in result["top_moves"]} == {max(12, depth)}


@pytest.mark.parametrize("recover", [False, True])
def test_search_without_valid_snapshot_retries_once(monkeypatch, recover):
    engine = FakeEngine([])
    install(monkeypatch, engine)
    streams = []

    async def analysis(board, limit, **kwargs):
        stream = FakeAnalysis(pair() if recover and streams else pair()[:1])
        streams.append(stream)
        return stream

    monkeypatch.setattr(engine, "analysis", analysis)
    if recover:
        result = classify_position(chess.STARTING_FEN)
        assert result["classification"] == "Flexible"
    else:
        with pytest.raises(StockfishAnalysisError, match="complete, consistent candidate batch"):
            classify_position(chess.STARTING_FEN)
    assert len(streams) == 2 and all(stream.stopped for stream in streams)
    assert engine.closed


@pytest.mark.parametrize("fen,reason", [
    ("7k/6Q1/5K2/8/8/8/8/8 b - - 0 1", "terminal_position"),
    ("7k/5K2/7Q/8/8/8/8/8 b - - 0 1", "terminal_position"),
    ("7k/8/6K1/8/8/8/8/8 b - - 0 1", "terminal_position"),
    ("7k/8/6K1/8/8/8/8/R7 b - - 0 1", "single_legal_move"),
    ("7k/8/5K2/8/8/8/8/R7 b - - 0 1", "fewer_than_five_legal_moves"),
])
def test_undefined_positions_do_not_launch_engine(monkeypatch, fen, reason):
    monkeypatch.setattr(StockfishSettings, "executable", lambda self: pytest.fail("No engine needed"))
    result = classify_position(fen)
    assert result["classification"] is None and result["unclassified_reason"] == reason
    assert result["delta_cp"] is None and result["delta_e_pp"] is None


@pytest.mark.parametrize("fen", ["invalid", chess.STARTING_BOARD_FEN, "8/8/8/8/8/8/8/8 w - - 0 1"])
def test_invalid_fen_rejected_before_engine(monkeypatch, fen):
    monkeypatch.setattr(StockfishSettings, "executable", lambda self: pytest.fail("Invalid FEN must not start engine"))
    with pytest.raises(InvalidPositionError):
        classify_position(fen)


@pytest.mark.parametrize("second_score,second_wins,label", [
    (chess.engine.Mate(5), 1000, "Forgiving"),
    (chess.engine.Cp(900), 950, "Critical"),
    (chess.engine.Cp(900), 900, "Critical"),
    (chess.engine.Cp(300), 800, "Critical"),
])
def test_mate_scores_have_no_invented_cp_gap(monkeypatch, second_score, second_wins, label):
    engine = FakeEngine([
        info("e2e4", None, (1000, 0, 0), 1, score=chess.engine.Mate(3)),
        info("d2d4", None, (second_wins, 0, 1000 - second_wins), 2, score=second_score),
        *[info(uci, None, (second_wins, 0, 1000 - second_wins), rank, score=second_score)
          for rank, uci in enumerate(["g1f3", "c2c4", "b1c3"], 3)],
    ])
    install(monkeypatch, engine)
    result = classify_position(chess.STARTING_FEN)
    assert result["classification"] == label and result["delta_cp"] is None
    assert result["unclassified_reason"] is None
    assert result["top_moves"][0]["score"]["mate"] == 3
    assert result["sharpness"]["capped_scores_cp"][0] == 2000


@pytest.mark.parametrize("change", ["missing_wdl", "bound", "missing_second", "duplicate", "illegal_pv", "invalid_wdl", "reversed_cp", "reversed_wdl"])
def test_incomplete_or_inconsistent_evidence_is_rejected(monkeypatch, change):
    infos = pair()
    if change == "missing_wdl":
        del infos[1]["wdl"]
    elif change == "bound":
        infos[1]["lowerbound"] = True
    elif change == "missing_second":
        infos.pop()
    elif change == "duplicate":
        infos[1]["pv"] = infos[0]["pv"]
    elif change == "illegal_pv":
        infos[0]["pv"] = [chess.Move.from_uci("e2e5")]
    elif change == "invalid_wdl":
        infos[0]["wdl"] = chess.engine.PovWdl(chess.engine.Wdl(600, 400, -1), chess.WHITE)
    elif change == "reversed_cp":
        infos[0]["score"] = chess.engine.PovScore(chess.engine.Cp(-50), chess.WHITE)
    elif change == "reversed_wdl":
        infos[0]["wdl"] = chess.engine.PovWdl(chess.engine.Wdl(0, 0, 1000), chess.WHITE)
    engine = FakeEngine(infos)
    install(monkeypatch, engine)
    with pytest.raises(StockfishAnalysisError):
        classify_position(chess.STARTING_FEN)
    assert engine.closed and engine.stream.stopped


def test_engine_without_native_wdl_is_rejected_and_closed(monkeypatch):
    engine = FakeEngine(pair())
    engine.options = {}
    install(monkeypatch, engine)
    with pytest.raises(StockfishUnavailableError, match="UCI_ShowWDL"):
        classify_position(chess.STARTING_FEN)
    assert engine.closed


@pytest.mark.parametrize("failure,expected", [(TimeoutError(), StockfishTimeoutError), (chess.engine.EngineTerminatedError(), StockfishAnalysisError)])
def test_engine_failures_close_transport(monkeypatch, failure, expected):
    engine = FakeEngine([], failure=failure)
    install(monkeypatch, engine)
    with pytest.raises(expected):
        classify_position(chess.STARTING_FEN)
    assert engine.closed and engine.stream.stopped


def test_stalled_stream_has_a_deadline(monkeypatch):
    engine = FakeEngine([], stall=True)
    install(monkeypatch, engine)
    timeout = asyncio.timeout
    requested = []

    def short_timeout(seconds):
        requested.append(seconds)
        return timeout(.01)

    monkeypatch.setattr(asyncio, "timeout", short_timeout)
    with pytest.raises(StockfishTimeoutError):
        classify_position(chess.STARTING_FEN, StockfishSettings(time_limit=2))
    assert requested == [7] and engine.closed and engine.stream.stopped


@pytest.mark.parametrize("analyzer,count", [(classify_position, 5), (analyze_position, 5)])
def test_real_stockfish_classification(analyzer, count):
    settings = StockfishSettings(depth=4, time_limit=2, threads=1, hash_mb=16)
    try:
        settings.executable()
    except StockfishUnavailableError:
        if os.getenv("REQUIRE_STOCKFISH_TEST") == "1":
            pytest.fail("The test image must include Stockfish.")
        pytest.skip("Install Stockfish to exercise the real classifier.")
    board = chess.Board()
    board.push_uci("e2e4")
    result = analyzer(board.fen(en_passant="fen"), settings)
    assert "Stockfish" in result["engine"] and result["perspective"] == "Black"
    assert result["classification"] in ("Forgiving", "Flexible", "Selective", "Demanding", "Critical")
    assert len(result["top_moves"]) == count
    first, second = result["top_moves"][:2]
    assert first["depth"] == second["depth"] > 0
    assert first["uci"] != second["uci"]
    assert result["delta_cp"] == first["score"]["cp"] - second["score"]["cp"]
    assert result["delta_e_pp"] == pytest.approx(100 * (first["expected_score"] - second["expected_score"]))
    for move in result["top_moves"]:
        assert chess.Move.from_uci(move["uci"]) in board.legal_moves
        assert sum(move["wdl"].values()) == 1000
        assert move["expected_score"] == pytest.approx(move["probabilities"]["win"] + .5 * move["probabilities"]["draw"])
    json.dumps(result, allow_nan=False)


def test_top_five_share_classification_and_relative_evaluations(monkeypatch):
    infos = [*pair()[:2], info("g1f3", 20, (540, 0, 460), 3),
             info("c2c4", 10, (530, 0, 470), 4), info("b1c3", 0, (520, 0, 480), 5)]
    engine = FakeEngine(infos)
    install(monkeypatch, engine)
    result = analyze_position(chess.STARTING_FEN)
    assert engine.request[2] == {"multipv": 5}
    assert result["classification"] == "Flexible" and result["decision_classification"] == "flexible"
    assert result["delta_cp"] == 35 and result["delta_e_pp"] == 5
    assert result["position_outlook"]["expected_score"] == .6
    assert result["permitted_candidate_uci"] == ["e2e4", "d2d4", "g1f3", "c2c4", "b1c3"]
    assert result["top_moves"][4]["relative_quality"] == {"cp_loss_from_best": 65, "expected_score_loss_pp": 8}


@pytest.mark.parametrize("fen,count", [
    ("7k/8/6K1/8/8/8/8/R7 b - - 0 1", 1),
    ("7k/8/5K2/8/8/8/8/R7 b - - 0 1", 2),
])
def test_coach_evidence_includes_all_moves_when_fewer_than_five(monkeypatch, fen, count):
    board = chess.Board(fen)
    engine = FakeEngine([info(move.uci(), 0, (0, 1000, 0), rank, color=chess.BLACK)
                         for rank, move in enumerate(board.legal_moves, 1)])
    install(monkeypatch, engine)
    result = analyze_position(fen)
    assert len(result["top_moves"]) == count and engine.request[2] == {"multipv": count}
    assert result["decision_classification"] is None and result["sharpness"]["score"] is None
    assert result["unclassified_reason"] == ("single_legal_move" if count == 1 else "fewer_than_five_legal_moves")


def test_terminal_coach_evidence_has_no_candidates(monkeypatch):
    monkeypatch.setattr(StockfishSettings, "executable", lambda self: pytest.fail("No engine needed"))
    result = analyze_position("7k/6Q1/5K2/8/8/8/8/8 b - - 0 1")
    assert result["decision_classification"] is None and result["position_outlook"] is None
    assert result["permitted_candidate_uci"] == [] and result["unclassified_reason"] == "terminal_position"
