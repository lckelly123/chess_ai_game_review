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
    return [info("e2e4", 30 + cp_gap, best_wdl, 1), info("d2d4", 30, second_wdl, 2)]


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
    (0, 500, 500, "Flexible"),
    (35, 600, 550, "Flexible"),  # Both inclusive boundaries, exactly 5 pp.
    (36, 600, 550, "Clear preference"),
    (35, 601, 550, "Clear preference"),
    (10, 799, 600, "Clear preference"),
    (10, 800, 600, "Critical"),  # Exactly 20 pp, irrespective of CP gap.
    (500, 1000, 0, "Critical"),
    (100, 1000, 1000, "Clear preference"),  # Large CP gap, unchanged expectation.
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
    assert fen == chess.STARTING_FEN and options == {"multipv": 2}
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
    assert [move["depth"] for move in result["top_moves"]] == [12, 12]
    assert result["top_moves"][0]["uci"] == "e2e4"


@pytest.mark.parametrize("fen,reason", [
    ("7k/6Q1/5K2/8/8/8/8/8 b - - 0 1", "terminal_position"),
    ("7k/5K2/7Q/8/8/8/8/8 b - - 0 1", "terminal_position"),
    ("7k/8/6K1/8/8/8/8/8 b - - 0 1", "terminal_position"),
    ("7k/8/6K1/8/8/8/8/R7 b - - 0 1", "single_legal_move"),
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
    (chess.engine.Mate(5), 1000, None),
    (chess.engine.Cp(900), 950, None),
    (chess.engine.Cp(900), 900, "Clear preference"),
    (chess.engine.Cp(300), 800, "Critical"),
])
def test_mate_scores_have_no_invented_cp_gap(monkeypatch, second_score, second_wins, label):
    engine = FakeEngine([
        info("e2e4", None, (1000, 0, 0), 1, score=chess.engine.Mate(3)),
        info("d2d4", None, (second_wins, 0, 1000 - second_wins), 2, score=second_score),
    ])
    install(monkeypatch, engine)
    result = classify_position(chess.STARTING_FEN)
    assert result["classification"] == label and result["delta_cp"] is None
    assert result["unclassified_reason"] == ("mate_score" if label is None else None)


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


@pytest.mark.parametrize("analyzer,count", [(classify_position, 2), (analyze_position, 5)])
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
    assert result["classification"] in ("Flexible", "Clear preference", "Critical")
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
    infos = [*pair(), info("g1f3", 20, (540, 0, 460), 3),
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
    assert result["decision_classification"] == (None if count == 1 else "flexible")
    assert result["unclassified_reason"] == ("single_legal_move" if count == 1 else None)


def test_terminal_coach_evidence_has_no_candidates(monkeypatch):
    monkeypatch.setattr(StockfishSettings, "executable", lambda self: pytest.fail("No engine needed"))
    result = analyze_position("7k/6Q1/5K2/8/8/8/8/8 b - - 0 1")
    assert result["decision_classification"] is None and result["position_outlook"] is None
    assert result["permitted_candidate_uci"] == [] and result["unclassified_reason"] == "terminal_position"
