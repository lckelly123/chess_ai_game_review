import asyncio
from threading import Event
from types import SimpleNamespace

import chess
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.coach.move_review import MoveReview
from backend.coach.player_move_quality import assess_player_move
from backend.coach.stockfish import StockfishAnalysisError, StockfishTimeoutError, StockfishUnavailableError
from backend.practice import create_practice_router, grade_attempt, saved_evidence


from backend.database import Database
from backend.chess_games import normalize_game
from backend.tests.test_app import raw_game


@pytest.fixture(autouse=True)
def practice_database(test_db_url):
    global practice_db_url
    practice_db_url = test_db_url


PGN = '1. e4 e5 2. Nf3 Nc6 *'


def candidate(uci, cp, rank):
    return {"uci": uci, "san": chess.Board().san(chess.Move.from_uci(uci)), "depth": 12, "rank": rank,
            "score": {"cp": cp, "mate": None, "bound": "exact"}}


def practice_app(analyzer=grade_attempt, pgn=PGN):
    original = MoveReview.from_game(pgn, 0)
    evidence = {"fen": original.position.fen, "perspective": original.position.side_to_move, "engine": "test",
                "top_moves": [candidate(uci, cp, rank) for rank, (uci, cp) in enumerate([
                    ('d2d4', 100), ('g1f3', 90), ('e2e4', -100), ('h2h3', 0), ('a2a3', -50)], 1)]}

    class SavedGames:
        def game(self, game_id):
            return {"pgn": pgn} if game_id == "saved" else None

        def game_analyses(self, game_id, current_pgn):
            assert current_pgn == pgn
            return {"white": {"moves": {"0": {"fen": original.position.fen,
                    "played_move": original.played_move_uci, "position_evidence": evidence}}}}

        def coach_feedback_for_reviews(self, keys, *, game_id=None):
            return {}

    durable = Database(practice_db_url)
    record = normalize_game(raw_game(pgn=pgn.replace('*', '1-0')), 'alice')
    record['id'] = 'saved'
    durable.save_import('alice', [record], 1)
    for name in ('review_sessions', 'start_review', 'reserve_review_submission', 'finish_review_submission'):
        setattr(SavedGames, name, staticmethod(getattr(durable, name)))
    app = FastAPI()
    app.state.db = SavedGames()
    app.include_router(create_practice_router(analyzer))
    return app, evidence


def payload(move, fen=chess.STARTING_FEN, original='e2e4'):
    return {"fen": fen, "original_move": original, "move": move}


def test_context_exposes_only_legal_moves_and_board_previews_without_engine_work():
    def forbidden(*args):
        pytest.fail('Opening practice must not run the engine.')

    app, _ = practice_app(forbidden)
    with TestClient(app) as client:
        data = client.get('/api/games/saved/practice/1').json()
        original = MoveReview.from_game(PGN, 1)
        assert data['fen'] == original.position.fen
        assert data['original_move'] == 'e7e5'
        assert len(data['legal_moves']) == 20
        assert set(data) == {'fen', 'original_move', 'legal_moves', 'review', 'reviews', 'analysis_revision'}
        option = next(move for move in data['legal_moves'] if move['uci'] == 'c7c5')
        board = chess.Board(original.position.fen)
        board.push_uci('c7c5')
        assert option['position']['fen'] == board.fen()
        assert option['position']['last_move'] == ['c7', 'c5']


@pytest.mark.parametrize('move,quality,accepted', [
    ('d2d4', 'good', True), ('g1f3', 'good', True),
    ('h2h3', 'inaccuracy', False), ('a2a3', 'mistake', False), ('e2e4', 'blunder', False),
])
def test_attempts_use_saved_root_and_accept_any_good_move(move, quality, accepted, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Live practice must not classify tactics or extend their lines.')
    monkeypatch.setattr('backend.tactics.classification.classify_review', forbidden)
    app, evidence = practice_app()
    with TestClient(app) as client:
        response = client.post('/api/games/saved/practice/0', json=payload(move))
        assert response.status_code == 200
        result = response.json()
        assert result['quality']['status'] == quality
        assert result['accepted'] is accepted
        assert result['fen'] == chess.STARTING_FEN and result['move'] == move
        assert result['original_move'] == 'e2e4'
        assert 'top_moves' not in result and 'position_evidence' not in result
        assert evidence['top_moves'][0]['uci'] == 'd2d4'
        assert client.get('/api/games/saved/practice/0').json()['fen'] == chess.STARTING_FEN


def test_move_outside_top_candidates_is_evaluated_from_the_same_root(monkeypatch):
    seen = []

    def evaluate(review, evidence):
        seen.append(review)
        assert review.played_move_uci not in [item['uci'] for item in evidence['top_moves']]
        return {'move_quality': assess_player_move(evidence['top_moves'][0], candidate(review.played_move_uci, 95, None))}

    monkeypatch.setattr('backend.practice.analyze_played_move', evaluate)
    app, _ = practice_app()
    with TestClient(app) as client:
        result = client.post('/api/games/saved/practice/0', json=payload('b1c3')).json()
        assert result['accepted'] is True
        assert seen[0].position.fen == chess.STARTING_FEN


def test_uncertain_comparison_never_completes_practice():
    app, evidence = practice_app()
    evidence['top_moves'][1]['depth'] = 11
    with TestClient(app) as client:
        result = client.post('/api/games/saved/practice/0', json=payload('g1f3')).json()
        assert result['quality']['status'] == 'uncertain'
        assert result['accepted'] is False


def test_black_attempt_uses_black_perspective_and_original_decision():
    app, evidence = practice_app()
    original = MoveReview.from_game(PGN, 1)
    evidence.update(fen=original.position.fen, perspective='Black')
    evidence['top_moves'][0].update(uci='c7c5', san='c5')
    evidence['top_moves'][1].update(uci='g8f6', san='Nf6')
    app.state.db.game_analyses = lambda *args: {'black': {'moves': {'1': {
        'fen': original.position.fen, 'played_move': 'e7e5', 'position_evidence': evidence}}}}
    with TestClient(app) as client:
        response = client.post('/api/games/saved/practice/1', json=payload('g8f6', original.position.fen, 'e7e5'))
        assert response.status_code == 200 and response.json()['accepted'] is True


def test_stale_game_evidence_falls_back_to_matching_coach_then_fresh_search(monkeypatch):
    app, evidence = practice_app()
    original = MoveReview.from_game(PGN, 0)
    stale = {**evidence, 'fen': 'different position'}
    app.state.db.game_analyses = lambda *args: {'white': {'moves': {'0': {
        'fen': original.position.fen, 'played_move': 'e2e4', 'position_evidence': stale}}}}
    app.state.db.coach_feedback_for_reviews = lambda keys, **kwargs: {keys[0]: {'position_evidence': evidence}}
    assert saved_evidence(app.state.db, 'saved', PGN, 0, original) is evidence
    app.state.db.coach_feedback_for_reviews = lambda keys, **kwargs: {keys[0]: {'position_evidence': stale}}
    assert saved_evidence(app.state.db, 'saved', PGN, 0, original) is None
    searched = []
    monkeypatch.setattr('backend.practice.analyze_position', lambda fen: searched.append(fen) or evidence)
    with TestClient(app) as client:
        assert client.post('/api/games/saved/practice/0', json=payload('g1f3')).json()['accepted'] is True
        assert searched == [chess.STARTING_FEN]


@pytest.mark.parametrize('pgn,ply,uci', [
    ('1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. O-O *', 6, 'e1g1'),
    ('1. e4 a6 2. e5 d5 3. exd6 *', 4, 'e5d6'),
    ('[SetUp "1"]\n[FEN "7k/P7/8/8/8/8/8/7K w - - 0 1"]\n\n1. a8=N *', 0, 'a7a8n'),
])
def test_special_move_options_have_exact_resulting_positions(pgn, ply, uci):
    app, _ = practice_app(pgn=pgn)
    with TestClient(app) as client:
        data = client.get(f'/api/games/saved/practice/{ply}').json()
        board = chess.Board(data['fen'])
        board.push_uci(uci)
        option = next(move for move in data['legal_moves'] if move['uci'] == uci)
        assert option['position']['fen'] == board.fen()
        if uci.startswith('a7a8'):
            assert {move['uci'] for move in data['legal_moves'] if move['uci'].startswith('a7a8')} == {'a7a8q', 'a7a8r', 'a7a8b', 'a7a8n'}


def test_illegal_moves_stale_positions_and_final_positions_do_not_run_engine():
    def forbidden(*args):
        pytest.fail('Invalid attempts must not run the engine.')

    app, _ = practice_app(forbidden)
    with TestClient(app) as client:
        for path, body, expected in [
            ('saved/0', payload('e2e5'), 422), ('saved/0', payload('e7e5'), 422),
            ('saved/0', payload('e2e4', fen='stale'), 409), ('saved/0', payload('e2e4', original='d2d4'), 409),
            ('saved/4', payload('e2e4'), 422), ('saved/-1', payload('e2e4'), 422),
            ('missing/0', payload('e2e4'), 404),
        ]:
            game_id, ply = path.split('/')
            assert client.post(f'/api/games/{game_id}/practice/{ply}', json=body).status_code == expected


@pytest.mark.parametrize('error,status', [(StockfishUnavailableError, 503), (StockfishTimeoutError, 504), (StockfishAnalysisError, 502)])
def test_engine_errors_are_recoverable_and_do_not_report_success(error, status):
    def fail(*args):
        raise error('private diagnostic')

    app, _ = practice_app(fail)
    with TestClient(app) as client:
        response = client.post('/api/games/saved/practice/0', json=payload('d2d4'))
        assert response.status_code == status and 'private diagnostic' not in response.text


def test_practice_shares_game_analysis_lock_and_rejects_overlapping_attempts():
    started, finish = Event(), Event()

    def slow(*args):
        started.set()
        assert finish.wait(5)
        return {'move_quality': {'status': 'good', 'winning_chances_loss_pp': 0}}

    app, _ = practice_app(slow)
    lock = asyncio.Lock()
    app.state.game_analysis = SimpleNamespace(engine_lock=lock)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            async with lock:
                assert (await client.post('/api/games/saved/practice/0', json=payload('d2d4'))).status_code == 409
            first = asyncio.create_task(client.post('/api/games/saved/practice/0', json=payload('d2d4')))
            try:
                assert await asyncio.to_thread(started.wait, 3)
                assert (await client.post('/api/games/saved/practice/0', json=payload('g1f3'))).status_code == 409
            finally:
                finish.set()
            assert (await first).status_code == 200

    asyncio.run(run())
