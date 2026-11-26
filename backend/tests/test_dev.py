import asyncio
from contextlib import asynccontextmanager
import threading

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.chess_games import normalize_game, replay
from backend.coach.context import context_key, previous_move_from_replay
from backend.coach.move_review import MoveReview
from backend.coach.position import CoachPosition
from backend.coach.responses import CoachAnalysis
from backend.database import Database
from backend.game_analysis import pgn_fingerprint
from backend.main import create_app
from backend.tests.test_app import raw_game
from backend.tests.test_game_analysis import FakeCoach, evidence, fake_coach, wait_completed
from backend.tests.test_multi_game import result as report_result


def seed(db, number=1):
    game = normalize_game(raw_game(number), 'alice')
    db.save_import('alice', [game], 123)
    fingerprint = pgn_fingerprint(game['pgn'])
    detail = replay(game['pgn'])
    for color, ply in [('white', 0), ('black', 1)]:
        review = MoveReview.from_game(game['pgn'], ply)
        db.begin_game_analysis(game['id'], color, fingerprint, 4 if color == 'white' else 3)
        db.save_game_analysis_move(game['id'], color, fingerprint, ply, {
            'fen': review.position.fen, 'played_move': review.played_move_uci, 'stockfish': evidence(review)})
        db.set_game_analysis_status(game['id'], color, fingerprint, 'completed', None)
        db.save_coach_feedback(asyncio.run(FakeCoach().analyze(review.position.fen, played_move=review.played_move_uci,
                               previous_move=previous_move_from_replay(detail, ply))), game_id=game['id'])
    return game


def add_report(db, name, game, username='alice'):
    db.begin_multi_game_analysis(name, username, {'summary': {}, 'mistakes_by_category': [
        {'category': 'unclassified', 'mistakes': [{'game': game['id']}]}]}, 'test', 'xhigh')
    db.complete_multi_game_analysis(name, report_result())


def test_single_reset_preserves_source_games_other_reviews_profiles_and_import_cache(test_db_url):
    db = Database(test_db_url)
    first, other = seed(db), seed(db, 2)
    db.save_cache('test-cache', {'keep': True}, None, None, 123)
    add_report(db, 'affected', first)
    # A report's coverage summary depends on this library even when its
    # individual mistake examples happen to come from a different game.
    add_report(db, 'coverage_only', other)
    db.save_import('bob', [other], 456)
    add_report(db, 'unaffected', other, username='bob')
    original_profiles = db.profiles()
    with TestClient(create_app(test_db_url)) as client:
        before = client.get(f'/api/games/{first["id"]}').json()
        other_before = client.get(f'/api/games/{other["id"]}').json()
        assert len(client.get('/api/dev/games').json()) == 2
        response = client.post('/api/dev/analysis/reset', json={'game_id': first['id']})
        assert response.status_code == 200
        assert response.json() == {'game_ids': [first['id']], 'games_reset': 1, 'engine_records': 2, 'coach_records': 2, 'reports': 2}
        after = client.get(f'/api/games/{first["id"]}').json()
        assert after == {**before, 'analysis_revision': 1, 'engine_analyses': {}, 'coach_responses': {}}
        assert client.get(f'/api/games/{other["id"]}').json() == other_before
        assert client.get(f'/api/games/{first["id"]}/pgn').text == first['pgn']
        assert client.get(f'/api/games/{first["id"]}/analysis?username=alice').json() is None
        assert db.multi_game_analyses('alice') == []
        assert [row['id'] for row in db.multi_game_analyses('bob')] == ['unaffected']
        assert db.profiles() == original_profiles
        assert db.cache('test-cache')['body'] == '{"keep": true}'
        assert client.post('/api/dev/analysis/reset', json={'game_id': first['id']}).json()['engine_records'] == 0
        assert client.post('/api/dev/analysis/reset', json={'game_id': 'missing'}).status_code == 404
        assert client.post('/api/dev/analysis/reset', json={'game_id': ''}).status_code == 422
    with TestClient(create_app(test_db_url)) as restarted:
        assert restarted.get(f'/api/games/{first["id"]}').json()['coach_responses'] == {}


def test_shared_legacy_feedback_is_available_only_to_games_that_have_not_been_reset(test_db_url):
    db = Database(test_db_url)
    first, other = seed(db), seed(db, 2)
    fen = replay(first['pgn'])['positions'][2]['fen']
    db.save_coach_feedback(CoachAnalysis('Legacy shared answer', 'legacy', 'test', CoachPosition.from_fen(fen), None))
    with TestClient(create_app(test_db_url, game_engine=evidence, coach_factory=fake_coach)) as client:
        assert client.get(f'/api/games/{first["id"]}').json()['coach_responses']['2']['text'] == 'Legacy shared answer'
        assert client.post('/api/dev/analysis/reset', json={'game_id': first['id']}).status_code == 200
        assert client.get(f'/api/games/{first["id"]}').json()['coach_responses'] == {}
        assert client.get(f'/api/games/{other["id"]}').json()['coach_responses']['2']['text'] == 'Legacy shared answer'
        assert client.post(f'/api/games/{first["id"]}/analysis', json={'username': 'alice'}).status_code == 202
        saved = wait_completed(client, first['id'])
        assert saved['coach_completed'] == 4
        assert len(client.get(f'/api/games/{first["id"]}').json()['coach_responses']) == 4
        assert client.get('/api/games?username=alice').json()[1]['analysis']['status'] == 'completed'
        assert client.get('/api/lessons?username=alice').json()['analyzed_games'] == 2


def test_old_worker_writes_cannot_change_a_fresh_run(test_db_url):
    db = Database(test_db_url)
    game = seed(db)
    old = pgn_fingerprint(game['pgn'])
    db.reset_analysis(game['id'])
    new = pgn_fingerprint(game['pgn'], 1)
    db.begin_game_analysis(game['id'], 'white', new, 4, 3)
    assert not db.save_game_analysis_move(game['id'], 'white', old, 0, {})
    assert not db.save_game_opponent_move(game['id'], 'white', old, 1, {})
    assert not db.save_game_coach_progress(game['id'], 'white', old, 4)
    db.set_game_analysis_status(game['id'], 'white', old, 'completed', None)
    answer = asyncio.run(FakeCoach().analyze(replay(game['pgn'])['positions'][0]['fen'], played_move='e2e4'))
    assert db.save_coach_feedback(answer, game_id=game['id'], expected_revision=0) is None
    assert db.game_analysis(game['id'], 'white', new)['status'] == 'queued'
    assert db.save_coach_feedback(answer, game_id=game['id'], expected_revision=1) is not None


def test_clear_all_removes_every_analysis_but_keeps_games_and_accounts(test_db_url):
    db = Database(test_db_url)
    first, other = seed(db), seed(db, 2)
    db.save_import('bob', [other], 456)
    add_report(db, 'report', first)
    db.save_coach_feedback(CoachAnalysis('Standalone review', 'standalone', 'test', CoachPosition.from_fen(
        replay(first['pgn'])['positions'][0]['fen']), None))
    profiles = db.profiles()
    with TestClient(create_app(test_db_url)) as client:
        result = client.post('/api/dev/analysis/reset', json={}).json()
        assert result['games_reset'] == 2 and result['coach_records'] == 5 and result['reports'] == 1
        assert db.profiles() == profiles
        for game in (first, other):
            detail = client.get(f'/api/games/{game["id"]}').json()
            assert detail['pgn'] == game['pgn'] and detail['coach_responses'] == {} and detail['engine_analyses'] == {}
        assert client.get('/api/lessons?username=alice').json()['errors']['total'] == 0
        assert db.multi_game_analyses('alice') == []
        assert client.post('/api/dev/analysis/reset', json={}).json()['coach_records'] == 0


@pytest.mark.parametrize('phase', ['engine', 'coach', 'multi-game'])
def test_reset_cancels_active_work_without_restoring_results(test_db_url, phase):
    entered, release = threading.Event(), threading.Event()
    cancelled = threading.Event()
    db = Database(test_db_url)
    game = seed(db)
    if phase != 'multi-game':
        db.reset_analysis(game['id'])

    def engine(review):
        if phase == 'engine' and not release.is_set():
            entered.set()
            assert release.wait(10)
        return evidence(review)

    class WaitingCoach(FakeCoach):
        async def analyze(self, *args, **kwargs):
            if phase == 'coach':
                entered.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise
            return await super().analyze(*args, **kwargs)

    @asynccontextmanager
    async def factory(settings, **kwargs):
        yield WaitingCoach()

    async def multi_analyzer(payload):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with TestClient(create_app(test_db_url, game_engine=engine, coach_factory=factory, multi_game_analyzer=multi_analyzer)) as client:
        endpoint = '/api/lessons/multi-game' if phase == 'multi-game' else f'/api/games/{game["id"]}/analysis'
        assert client.post(endpoint, json={'username': 'alice'}).status_code == 202
        assert entered.wait(5)
        try:
            assert client.post('/api/dev/analysis/reset', json={'game_id': game['id']}).status_code == 200
        finally:
            release.set()
        detail = client.get(f'/api/games/{game["id"]}').json()
        assert detail['engine_analyses'] == {} and detail['coach_responses'] == {}
        assert db.multi_game_analyses('alice') == []
        if phase != 'engine':
            assert cancelled.is_set()


def test_failed_reset_rolls_back_the_entire_transaction(test_db_url):
    db = Database(test_db_url)
    game = seed(db)
    before = db.game_analyses(game['id'], game['pgn'])
    with db.connection() as connection:
        connection.execute("""CREATE FUNCTION refuse_reset() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'test reset failure'; END $$;
            CREATE TRIGGER refuse_reset BEFORE DELETE ON coach_feedback FOR EACH STATEMENT EXECUTE FUNCTION refuse_reset();""")
    with pytest.raises(psycopg.Error):
        db.reset_analysis(game['id'])
    assert db.game(game['id'])['analysis_revision'] == 0
    assert db.game_analyses(game['id'], game['pgn']) == before
