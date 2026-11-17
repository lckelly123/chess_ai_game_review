import asyncio
import json
import os
from threading import Event

import chess
import chess.engine
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.coach.move_review import MoveReview, NoPlayedMoveError
from backend.coach.position import InvalidPositionError
from backend.coach.preparation_routes import create_preparation_router
from backend.coach.stockfish import (
    StockfishAnalysisError, StockfishSettings, StockfishTimeoutError,
    StockfishUnavailableError, analyze_move,
)


PGN = '[White "alice"]\n[Black "bob"]\n\n1. e4 e5 2. Nf3 Nc6 *'


def test_next_move_uses_current_position_not_the_previous_move():
    first = MoveReview.from_game(PGN, 0)
    assert first.position.fen == chess.STARTING_FEN
    assert first.played_move_uci == "e2e4"
    second = MoveReview.from_game(PGN, 1)
    board = chess.Board()
    board.push_uci("e2e4")
    assert second.position.fen == board.fen()
    assert second.position.side_to_move == "Black"
    assert second.played_move_uci == "e7e5"
    assert second.played_move_san == "e5"
    assert "4  . . . . P . . ." in second.position.ascii_board
    assert MoveReview.from_game(PGN, 3).played_move_uci == "b8c6"


def test_final_position_has_no_move_even_if_play_could_continue():
    with pytest.raises(NoPlayedMoveError, match="no next recorded move"):
        MoveReview.from_game(PGN, 4)
    for ply in (-1, 5, True):
        with pytest.raises(InvalidPositionError):
            MoveReview.from_game(PGN, ply)


def test_review_identity_includes_move_and_complete_fen():
    first = MoveReview.from_fen(chess.STARTING_FEN, "e2e4")
    assert first.review_key == MoveReview.from_game(PGN, 0).review_key
    assert first.review_key != MoveReview.from_fen(chess.STARTING_FEN, "d2d4").review_key
    other_clock = chess.STARTING_FEN.rsplit(" ", 1)[0] + " 2"
    assert first.review_key != MoveReview.from_fen(other_clock, "e2e4").review_key
    assert json.loads(json.dumps(first.as_dict()))["played_move"] == {"uci": "e2e4", "san": "e4"}


@pytest.mark.parametrize("pgn,ply,uci,san", [
    ('1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. O-O *', 6, "e1g1", "O-O"),
    ('1. e4 a6 2. e5 d5 3. exd6 *', 4, "e5d6", "exd6"),
    ('[SetUp "1"]\n[FEN "7k/P7/8/8/8/8/8/7K w - - 0 1"]\n\n1. a8=N *', 0, "a7a8n", "a8=N"),
])
def test_special_moves_are_derived_from_the_pre_move_board(pgn, ply, uci, san):
    review = MoveReview.from_game(pgn, ply)
    assert (review.played_move_uci, review.played_move_san) == (uci, san)


@pytest.mark.parametrize("move", ["e2e5", "e7e5", "0000", "e4", "invalid"])
def test_illegal_or_non_uci_moves_rejected(move):
    with pytest.raises(InvalidPositionError):
        MoveReview.from_fen(chess.STARTING_FEN, move)


class FakeEngine:
    id = {"name": "Stockfish test"}

    def __init__(self, top, fallback=None, failure=None):
        self.top = top
        self.fallback = fallback
        self.failure = failure
        self.calls = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def configure(self, options):
        self.options = options

    def analyse(self, board, limit, **kwargs):
        self.calls.append((board.fen(), limit, kwargs))
        if self.failure:
            raise self.failure
        return self.fallback if "root_moves" in kwargs else self.top


def engine_info(uci, score=chess.engine.Cp(25), color=chess.WHITE):
    return {"pv": [chess.Move.from_uci(uci)], "score": chess.engine.PovScore(score, color), "depth": 12}


def install_fake(monkeypatch, engine):
    monkeypatch.setattr(StockfishSettings, "executable", lambda self: "test-stockfish")
    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", lambda *args, **kwargs: engine)


def test_move_in_top_eight_reuses_engine_result(monkeypatch):
    moves = ["e2e4", "d2d4", "g1f3", "c2c4", "b1c3", "g2g3", "b2b3", "e2e3"]
    engine = FakeEngine([engine_info(move) for move in moves])
    install_fake(monkeypatch, engine)
    evidence = analyze_move(MoveReview.from_fen(chess.STARTING_FEN, "e2e4"))
    assert len(engine.calls) == 1
    assert engine.calls[0][2] == {"multipv": 8}
    assert evidence["played_move"] == evidence["top_moves"][0]
    assert evidence["played_move_in_top"] is True
    assert evidence["played_move"]["score"] == {"cp": 25, "mate": None, "bound": "exact"}
    assert engine.closed


def test_outside_top_eight_searches_same_root_with_same_limits_for_black(monkeypatch):
    review = MoveReview.from_game(PGN, 1)
    moves = ["e7e5", "c7c5", "e7e6", "c7c6", "d7d5", "g8f6", "b8c6", "g7g6"]
    # Scores deliberately expressed from White's perspective; output must flip.
    fallback = engine_info("a7a5", chess.engine.Mate(3))
    fallback["upperbound"] = True
    engine = FakeEngine([engine_info(move) for move in moves], fallback)
    install_fake(monkeypatch, engine)
    evidence = analyze_move(MoveReview.from_fen(review.position.fen, "a7a5"))
    assert len(engine.calls) == 2
    assert engine.calls[0][0] == engine.calls[1][0] == review.position.fen
    assert engine.calls[0][1] == engine.calls[1][1]
    assert engine.calls[1][2] == {"root_moves": [chess.Move.from_uci("a7a5")]}
    assert evidence["perspective"] == "Black"
    assert evidence["top_moves"][0]["score"]["cp"] == -25
    assert evidence["played_move"]["score"]["mate"] == -3
    assert evidence["played_move"]["score"]["bound"] == "lower"
    assert evidence["played_move"]["rank"] is None
    assert evidence["played_move_in_top"] is False
    assert engine.closed


def test_fewer_than_eight_legal_moves(monkeypatch):
    fen = "7k/8/6K1/8/8/8/8/8 b - - 0 1"
    engine = FakeEngine([engine_info("h8g8", chess.engine.Cp(0), chess.BLACK)])
    install_fake(monkeypatch, engine)
    evidence = analyze_move(MoveReview.from_fen(fen, "h8g8"))
    assert engine.calls[0][2]["multipv"] == 1
    assert len(evidence["top_moves"]) == 1


@pytest.mark.parametrize("failure,expected", [
    (TimeoutError(), StockfishTimeoutError),
    (chess.engine.EngineTerminatedError(), StockfishAnalysisError),
])
def test_engine_cleanup_on_failure(monkeypatch, failure, expected):
    engine = FakeEngine([], failure=failure)
    install_fake(monkeypatch, engine)
    with pytest.raises(expected):
        analyze_move(MoveReview.from_game(PGN, 0))
    assert engine.closed


def test_missing_candidates_are_not_presented_as_complete(monkeypatch):
    engine = FakeEngine([engine_info("e2e4")])
    install_fake(monkeypatch, engine)
    with pytest.raises(StockfishAnalysisError, match="all requested"):
        analyze_move(MoveReview.from_game(PGN, 0))
    assert engine.closed


def test_illegal_engine_variation_is_rejected(monkeypatch):
    engine = FakeEngine([engine_info("e2e5")])
    install_fake(monkeypatch, engine)
    with pytest.raises(StockfishAnalysisError, match="invalid principal variation"):
        analyze_move(MoveReview.from_game(PGN, 0))
    assert engine.closed


@pytest.mark.parametrize("settings", [{"depth": 0}, {"time_limit": float("nan")}, {"time_limit": 0}, {"threads": 0}, {"hash_mb": 1}])
def test_invalid_engine_resource_settings(settings):
    with pytest.raises(StockfishUnavailableError):
        StockfishSettings(**settings)


def preparation_app(analyzer):
    app = FastAPI()
    app.include_router(create_preparation_router(analyzer))

    class SavedGames:
        def game(self, game_id):
            return {"pgn": PGN} if game_id == "saved" else None

    app.state.db = SavedGames()
    return app


def test_endpoint_derives_position_and_move_from_saved_game():
    calls = []

    def analyzer(review):
        calls.append(review)
        return {"engine": "test"}

    with TestClient(preparation_app(analyzer)) as client:
        response = client.post("/api/coach/prepare-move", json={"game_id": "saved", "ply": 1})
        assert response.status_code == 200
        assert response.json()["played_move"]["uci"] == "e7e5"
        assert response.json()["side_to_move"] == "Black"
        assert response.json()["stockfish"]["engine"] == "test"
        assert len(calls) == 1
        for payload, status in [
            ({"game_id": "missing", "ply": 0}, 404),
            ({"game_id": "saved", "ply": 4}, 422),
            ({"game_id": "saved", "ply": 5}, 422),
            ({"game_id": "saved", "ply": -1}, 422),
            ({"game_id": "saved", "ply": True}, 422),
            ({"game_id": "saved", "ply": 0, "played_move": "d2d4"}, 422),
        ]:
            assert client.post("/api/coach/prepare-move", json=payload).status_code == status
        assert len(calls) == 1


@pytest.mark.parametrize("error,status", [
    (StockfishUnavailableError, 503), (StockfishTimeoutError, 504), (StockfishAnalysisError, 502),
])
def test_endpoint_engine_errors_are_safe(error, status):
    def analyzer(review):
        raise error("private configuration")

    with TestClient(preparation_app(analyzer)) as client:
        response = client.post("/api/coach/prepare-move", json={"game_id": "saved", "ply": 0})
        assert response.status_code == status
        assert "private configuration" not in response.text


def test_endpoint_rejects_overlapping_engine_work():
    started, finish = Event(), Event()

    def analyzer(review):
        started.set()
        assert finish.wait(5)
        return {}

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(preparation_app(analyzer)), base_url="http://test") as client:
            payload = {"game_id": "saved", "ply": 0}
            first = asyncio.create_task(client.post("/api/coach/prepare-move", json=payload))
            try:
                assert await asyncio.to_thread(started.wait, 3)
                assert (await client.post("/api/coach/prepare-move", json=payload)).status_code == 409
            finally:
                finish.set()
            assert (await first).status_code == 200
    asyncio.run(run())


def test_real_stockfish_smoke():
    settings = StockfishSettings(depth=4, time_limit=2, threads=1, hash_mb=16)
    try:
        settings.executable()
    except StockfishUnavailableError:
        if os.getenv("REQUIRE_STOCKFISH_TEST") == "1":
            pytest.fail("The test image must include Stockfish.")
        pytest.skip("Install Stockfish to exercise the real engine.")
    review = MoveReview.from_game(PGN, 1)
    evidence = analyze_move(review, settings)
    assert "Stockfish" in evidence["engine"]
    assert evidence["perspective"] == "Black"
    assert len(evidence["top_moves"]) == 8
    assert evidence["played_move"]["uci"] == "e7e5"
    json.dumps(evidence)
    excluded = next(move for move in chess.Board(review.position.fen).legal_moves
                    if move.uci() not in {item["uci"] for item in evidence["top_moves"]})
    outside = analyze_move(MoveReview.from_fen(review.position.fen, excluded.uci()), settings)
    assert outside["played_move"]["uci"] == excluded.uci()
    assert outside["played_move_in_top"] is False
    assert outside["played_move"]["rank"] is None
