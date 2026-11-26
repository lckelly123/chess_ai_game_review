import asyncio
import time
from datetime import datetime, timezone

import chess
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.chess_games import replay
from backend.database import Database
from backend.importer import ChessComImporter
from backend.main import create_app

PGN = '[White "alice"]\n[Black "bob"]\n[Result "1-0"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. O-O 1-0'


def raw_game(number=1, **overrides):
    return {"url": f"https://www.chess.com/game/live/{number}", "pgn": PGN,
            "white": {"username": "alice", "rating": 1300},
            "black": {"username": "bob", "rating": 1400}, "end_time": number,
            "rules": "chess", "time_class": "rapid", "time_control": "600", **overrides}


def wait_job(client, job):
    for _ in range(500):
        current = client.get(f'/api/imports/{job["id"]}').json()
        if current["status"] in {"completed", "failed"}:
            return current
        time.sleep(.01)
    pytest.fail("Import did not finish")


def test_import_replay_dedup_and_persistence(test_db_url):
    requests = []
    def upstream(request):
        requests.append(str(request.url))
        if request.url.path.endswith('/archives'):
            return httpx.Response(200, json={"archives": ["https://api.chess.com/pub/player/alice/games/2026/10", "https://api.chess.com/pub/player/alice/games/2026/11"]})
        if request.url.path.endswith('/2026/11'):
            return httpx.Response(200, json={"games": [raw_game(2), raw_game(3), raw_game(99, rules="chess960")]})
        if request.url.path.endswith('/2026/10'):
            return httpx.Response(200, json={"games": [raw_game(1)]})
        return httpx.Response(200, json={"username": "alice"})
    path = test_db_url
    with TestClient(create_app(path, httpx.MockTransport(upstream))) as client:
        response = client.post('/api/imports', json={"username": " ALICE ", "limit": 3})
        assert response.status_code == 202
        job = wait_job(client, response.json())
        assert job['status'] == 'completed' and job['added'] == 3 and job['skipped'] == 1
        games = client.get('/api/games?username=alice').json()
        assert [g['end_time'] for g in games] == [3, 2, 1]
        detail = client.get(f'/api/games/{games[0]["id"]}').json()
        assert len(detail['positions']) == 8
        assert detail['moves'][-1]['san'] == 'O-O'
        board = chess.Board(detail['positions'][-1]['fen'])
        assert board.piece_at(chess.G1) == chess.Piece(chess.KING, chess.WHITE)
        assert board.piece_at(chess.F1) == chess.Piece(chess.ROOK, chess.WHITE)
        assert board.piece_at(chess.H1) is None
        assert client.get(f'/api/games/{games[0]["id"]}/pgn').text == PGN
        request_count = len(requests)
        repeated = wait_job(client, client.post('/api/imports', json={"username": "alice", "limit": 3}).json())
        assert repeated['added'] == 0
        assert len(requests) == request_count  # Repeated imports use the cache.
    with TestClient(create_app(path, httpx.MockTransport(upstream))) as restarted:
        assert len(restarted.get('/api/games?username=alice').json()) == 3
        assert restarted.get('/api/profiles').json()[0]['game_count'] == 3


def test_import_limit_avoids_older_archives(test_db_url):
    paths = []
    def upstream(request):
        paths.append(request.url.path)
        if request.url.path.endswith('/archives'):
            return httpx.Response(200, json={"archives": ["https://api.chess.com/pub/player/alice/games/2026/10", "https://api.chess.com/pub/player/alice/games/2026/11"]})
        if request.url.path.endswith('/2026/11'):
            return httpx.Response(200, json={"games": [raw_game(1), raw_game(2)]})
        return httpx.Response(200, json={})
    with TestClient(create_app(test_db_url, httpx.MockTransport(upstream))) as client:
        job = wait_job(client, client.post('/api/imports', json={"username": "alice", "limit": 1}).json())
        assert job['added'] == 1
        assert not any(path.endswith('/2026/10') for path in paths)
        assert client.get('/api/games?username=alice').json()[0]['end_time'] == 2


@pytest.mark.parametrize('status', [404, 403, 429, 500])
def test_upstream_errors_are_actionable_and_do_not_create_profiles(test_db_url, status):
    transport = httpx.MockTransport(lambda r: httpx.Response(status, headers={"Retry-After": "120"}))
    with TestClient(create_app(test_db_url, transport)) as client:
        job = wait_job(client, client.post('/api/imports', json={"username": "alice"}).json())
        assert job['status'] == 'failed'
        assert job['message']
        assert client.get('/api/profiles').json() == []


def test_empty_and_untrusted_archives(test_db_url):
    paths = []
    def upstream(request):
        paths.append(str(request.url))
        return httpx.Response(200, json={"archives": ["http://127.0.0.1/private", "https://evil.example/games/2026/11"]})
    with TestClient(create_app(test_db_url, httpx.MockTransport(upstream))) as client:
        job = wait_job(client, client.post('/api/imports', json={"username": "alice"}).json())
        assert job['status'] == 'completed' and job['found'] == 0
        assert all(url.startswith('https://api.chess.com/') for url in paths)


def test_malformed_pgn_skipped_without_breaking_import(test_db_url):
    def upstream(request):
        if request.url.path.endswith('/archives'):
            return httpx.Response(200, json={"archives": ["https://api.chess.com/pub/player/alice/games/2026/11"]})
        if request.url.path.endswith('/2026/11'):
            return httpx.Response(200, json={"games": [raw_game(2, pgn='[Result "1-0"]\n1. e5 1-0'), raw_game(1)]})
        return httpx.Response(200, json={})
    with TestClient(create_app(test_db_url, httpx.MockTransport(upstream))) as client:
        job = wait_job(client, client.post('/api/imports', json={"username": "alice"}).json())
        assert job['added'] == 1 and job['skipped'] == 1


def test_request_validation_and_missing_resources(test_db_url):
    with TestClient(create_app(test_db_url)) as client:
        for body in [{"username": "../private"}, {"username": "alice", "limit": 101}, {"username": ""}]:
            assert client.post('/api/imports', json=body).status_code == 422
        assert client.get('/api/games/missing').status_code == 404
        assert client.get('/api/imports/missing').status_code == 404
        assert client.get('/api/unknown').status_code == 404


def test_conditional_cache_revalidation(test_db_url):
    db = Database(test_db_url)
    url = 'https://api.chess.com/pub/player/alice'
    db.save_cache(url, {"username": "alice"}, '"v1"', None, 0)
    def upstream(request):
        assert request.headers['If-None-Match'] == '"v1"'
        return httpx.Response(304)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            assert await ChessComImporter(db, client).get(url) == {"username": "alice"}
    asyncio.run(run())
    assert db.cache(url)['fetched'] > 0


def test_retry_after_rate_limit(test_db_url):
    attempts = []
    def upstream(request):
        attempts.append(request)
        return httpx.Response(429, headers={"Retry-After": "0"}) if len(attempts) == 1 else httpx.Response(200, json={"username": "alice"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
            assert await ChessComImporter(Database(test_db_url), client).get('https://api.chess.com/pub/player/alice') == {"username": "alice"}
    asyncio.run(run())
    assert len(attempts) == 2


def test_en_passant_and_promotion_replay():
    ep = replay('1. e4 a6 2. e5 d5 3. exd6 *')
    board = chess.Board(ep['positions'][-1]['fen'])
    assert board.piece_at(chess.D6) == chess.Piece(chess.PAWN, chess.WHITE)
    assert board.piece_at(chess.D5) is None
    promotion = replay('[SetUp "1"]\n[FEN "7k/P7/8/8/8/8/8/7K w - - 0 1"]\n1. a8=Q+ *')
    assert chess.Board(promotion['positions'][-1]['fen']).piece_at(chess.A8) == chess.Piece(chess.QUEEN, chess.WHITE)
    assert promotion['positions'][-1]['check_square'] == 'h8'


def test_nonstandard_starting_ply_is_preserved():
    detail = replay('[SetUp "1"]\n[FEN "7k/8/8/8/8/8/p7/7K b - - 0 23"]\n23... a1=Q+ *')
    assert detail['moves'][0]['number'] == 23
    assert detail['moves'][0]['color'] == 'black'
    assert detail['positions'][0]['fen'].split()[1] == 'b'


def test_failed_import_preserves_existing_library(test_db_url):
    from backend.chess_games import normalize_game
    path = test_db_url
    db = Database(path)
    db.save_import('alice', [normalize_game(raw_game(99), 'alice')], 1)
    def upstream(request):
        if request.url.path.endswith('/archives'):
            return httpx.Response(200, json={"archives": ["https://api.chess.com/pub/player/alice/games/2026/10", "https://api.chess.com/pub/player/alice/games/2026/11"]})
        if request.url.path.endswith('/2026/11'):
            return httpx.Response(200, json={"games": [raw_game(2)]})
        if request.url.path.endswith('/2026/10'):
            return httpx.Response(500, headers={"Retry-After": "120"})
        return httpx.Response(200, json={})
    with TestClient(create_app(path, httpx.MockTransport(upstream))) as client:
        job = wait_job(client, client.post('/api/imports', json={"username": "alice"}).json())
        assert job['status'] == 'failed'
        assert [game['end_time'] for game in client.get('/api/games?username=alice').json()] == [99]
        assert client.get('/api/profiles').json()[0]['last_synced'] == 1


def test_concurrent_imports_are_coordinated(test_db_url):
    async def upstream(request):
        await asyncio.sleep(.15)
        return httpx.Response(200, json={"archives": []})
    with TestClient(create_app(test_db_url, httpx.MockTransport(upstream))) as client:
        first = client.post('/api/imports', json={"username": "alice"}).json()
        duplicate = client.post('/api/imports', json={"username": "alice"}).json()
        assert duplicate['id'] == first['id']
        assert client.post('/api/imports', json={"username": "bob"}).status_code == 409
        assert wait_job(client, first)['status'] == 'completed'


def timestamp(year, month, day):
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


def test_sync_starts_with_50_and_revalidates_recent_cache_without_duplicates(test_db_url):
    calls = []
    published = [raw_game(i, end_time=timestamp(2026, 11, 1) + i) for i in range(1, 81)]
    def upstream(request):
        calls.append(request)
        if request.url.path.endswith('/archives'):
            return httpx.Response(200, json={"archives": ["https://api.chess.com/pub/player/alice/games/2026/11"]})
        if request.url.path.endswith('/2026/11'):
            return httpx.Response(200, json={"games": published}, headers={"ETag": '"games"'})
        return httpx.Response(200, json={"username": "alice"})

    with TestClient(create_app(test_db_url, httpx.MockTransport(upstream))) as client:
        def sync():
            return wait_job(client, client.post('/api/imports', json={"username": "alice", "sync": True}).json())
        assert sync()['added'] == 50
        assert len(client.get('/api/games?username=alice').json()) == 50
        published.append(raw_game(81, end_time=timestamp(2026, 11, 1) + 81))
        assert sync()['added'] == 1  # Does not silently serve the 15-minute cache.
        assert calls[-1].headers['If-None-Match'] == '"games"'
        assert sync()['added'] == 0
        assert len(client.get('/api/games?username=alice').json()) == 51  # No older-history backfill.


def test_sync_catches_more_than_100_games_and_new_archive_months(test_db_url):
    from backend.chess_games import normalize_game
    db = Database(test_db_url)
    first = raw_game(1, end_time=timestamp(2024, 1, 15))
    db.save_import('alice', [normalize_game(first, 'alice')], timestamp(2026, 11, 1))
    # A stale archive index must not hide months that appeared since the last visit.
    index = 'https://api.chess.com/pub/player/alice/games/archives'
    db.save_cache(index, {"archives": [index.replace('/archives', '/2024/01')]}, '"old"', None, time.time())
    paths = []
    def upstream(request):
        paths.append(request.url.path)
        if request.url.path.endswith('/archives'):
            assert request.headers['If-None-Match'] == '"old"'
            return httpx.Response(200, json={"archives": [
                index.replace('/archives', f'/{year}/{month:02d}')
                for year in range(2024, 2027) for month in range(1, 13)]})
        if '/games/' in request.url.path:
            year, month = map(int, request.url.path.rsplit('/', 2)[-2:])
            number = year * 1000 + month * 10
            return httpx.Response(200, json={"games": [raw_game(number + i, end_time=timestamp(year, month, 16) + i) for i in range(4)]})
        return httpx.Response(200, json={})
    with TestClient(create_app(test_db_url, httpx.MockTransport(upstream))) as client:
        job = wait_job(client, client.post('/api/imports', json={"username": "alice", "sync": True}).json())
        assert job['status'] == 'completed' and job['added'] == 144
        assert len(client.get('/api/games?username=alice').json()) == 145
        assert any(path.endswith('/2024/01') for path in paths)  # No 24-month catch-up cutoff.


def test_sync_revisits_previous_month_for_delayed_games(test_db_url):
    from backend.chess_games import normalize_game
    db = Database(test_db_url)
    db.save_import('alice', [normalize_game(raw_game(1, end_time=timestamp(2026, 10, 29)), 'alice'),
                             normalize_game(raw_game(3, end_time=timestamp(2026, 11, 1)), 'alice')], 1)
    def upstream(request):
        if request.url.path.endswith('/archives'):
            return httpx.Response(200, json={"archives": [f'https://api.chess.com/pub/player/alice/games/2026/{month}' for month in ['10', '11']]})
        if request.url.path.endswith('/2026/10'):
            return httpx.Response(200, json={"games": [raw_game(2, end_time=timestamp(2026, 10, 31))]})
        if request.url.path.endswith('/2026/11'):
            return httpx.Response(200, json={"games": [raw_game(4, end_time=timestamp(2026, 11, 1))]})
        return httpx.Response(200, json={})
    with TestClient(create_app(test_db_url, httpx.MockTransport(upstream))) as client:
        job = wait_job(client, client.post('/api/imports', json={"username": "alice", "sync": True}).json())
        assert job['added'] == 2  # Includes another game with the same completion time.


def test_failed_sync_preserves_library_and_last_success(test_db_url):
    from backend.chess_games import normalize_game
    db = Database(test_db_url)
    db.save_import('alice', [normalize_game(raw_game(), 'alice')], 123)
    transport = httpx.MockTransport(lambda request: httpx.Response(429, headers={"Retry-After": "120"}))
    with TestClient(create_app(test_db_url, transport)) as client:
        job = wait_job(client, client.post('/api/imports', json={"username": "alice", "sync": True}).json())
        assert job['status'] == 'failed'
        assert len(client.get('/api/games?username=alice').json()) == 1
        assert client.get('/api/profiles').json()[0]['last_synced'] == 123


def test_account_switch_queues_sync_and_coalesces_reloads(test_db_url):
    async def upstream(request):
        await asyncio.sleep(.05)
        return httpx.Response(200, json={"archives": []})
    with TestClient(create_app(test_db_url, httpx.MockTransport(upstream))) as client:
        first = client.post('/api/imports', json={"username": "alice", "sync": True}).json()
        second = client.post('/api/imports', json={"username": "bob", "sync": True})
        assert second.status_code == 202
        repeated = client.post('/api/imports', json={"username": "bob", "sync": True}).json()
        assert repeated['id'] == second.json()['id']
        assert wait_job(client, first)['status'] == 'completed'
        assert wait_job(client, repeated)['status'] == 'completed'


def test_previously_empty_account_catches_all_new_games(test_db_url):
    Database(test_db_url).save_import('alice', [], timestamp(2026, 10, 1))
    def upstream(request):
        if request.url.path.endswith('/archives'):
            return httpx.Response(200, json={"archives": ['https://api.chess.com/pub/player/alice/games/2026/11']})
        if request.url.path.endswith('/2026/11'):
            return httpx.Response(200, json={"games": [raw_game(i, end_time=timestamp(2026, 11, 1) + i) for i in range(120)]})
        return httpx.Response(200, json={})
    with TestClient(create_app(test_db_url, httpx.MockTransport(upstream))) as client:
        job = wait_job(client, client.post('/api/imports', json={"username": "alice", "sync": True}).json())
        assert job['added'] == 120
