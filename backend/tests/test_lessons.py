from copy import deepcopy

from fastapi.testclient import TestClient

from backend.chess_games import normalize_game
from backend.coach.classification import CLASSIFICATION_VERSION
from backend.coach.move_review import MoveReview
from backend.coach.responses import CoachAnalysis
from backend.database import Database
from backend.game_analysis import pgn_fingerprint
from backend.lessons import lesson_analytics
from backend.main import create_app
from backend.tests.test_app import raw_game
from backend.tests.test_game_analysis import evidence

PGN = '1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. d3 Nf6 5. O-O *'


def saved_move(ply, cp, pgn=PGN):
    review = MoveReview.from_game(pgn, ply)
    engine = evidence(review)
    engine['played_move']['score']['cp'] = cp
    return {'fen': review.position.fen, 'played_move': review.played_move_uci, 'stockfish': engine}


def feedback(category, subcategory):
    return {'classification_version': CLASSIFICATION_VERSION, 'teaching': {'move_evaluation': {'mistake_classification':
        {'category': category, 'subcategory': subcategory} if category else None}}}


class MemoryDatabase:
    def __init__(self):
        self.records = [{'id': 'game-one', 'metadata': {'white': 'alice', 'black': 'bob'},
                         'pgn': PGN, 'pgn_hash': pgn_fingerprint(PGN),
                         'moves': {str(ply): saved_move(ply, cp)
                                   for ply, cp in [(0, 100), (2, 30), (4, -30), (6, -100), (8, None)]}}]
        moves = self.records[0]['moves']
        self.feedback = {(moves['2']['fen'], moves['2']['played_move']): feedback('positional', 'knight'),
                         (moves['4']['fen'], moves['4']['played_move']): feedback('tactical_miss', 'fork'),
                         (moves['6']['fen'], moves['6']['played_move']): feedback('tactical_allowed', 'pin_skewer')}

    def lesson_games(self, username):
        return self.records

    def coach_feedback_for_reviews(self, reviews):
        return {key: value for key, value in self.feedback.items() if key in reviews}


def category(result, key):
    return next(group for group in result['categories'] if group['key'] == key)


def test_breakdown_counts_errors_in_each_new_category():
    db = MemoryDatabase()
    before = deepcopy(db.records)
    result = lesson_analytics(db, ' ALICE ')
    assert result['username'] == 'alice'
    assert result['imported_games'] == result['analyzed_games'] == 1
    assert result['analyzed_moves'] == 5
    assert result['errors'] == {'inaccuracy': 1, 'mistake': 1, 'blunder': 1, 'total': 3}
    assert category(result, 'tactical_miss')['counts'] == {'inaccuracy': 0, 'mistake': 1, 'blunder': 0, 'total': 1}
    assert category(result, 'tactical_allowed')['counts']['blunder'] == 1
    assert category(result, 'positional')['counts']['inaccuracy'] == 1
    assert len(category(result, 'positional')['subcategories']) == 6
    assert all(row['key'] != 'unspecified' for group in result['categories'] for row in group['subcategories'])
    assert result['unclassified']['total'] == result['pending_reviews'] == 0
    assert db.records == before  # No regrading or aggregation writes to storage.


def test_missing_and_unsupported_coach_labels_do_not_disappear_from_totals():
    db = MemoryDatabase()
    keys = list(db.feedback)
    del db.feedback[keys[0]]
    db.feedback[keys[1]] = feedback(None, None)
    db.feedback[keys[2]] = feedback('tactical_allowed', 'unsupported_label')
    result = lesson_analytics(db, 'alice')
    assert result['unclassified'] == result['errors']
    assert result['pending_reviews'] == 1  # Explicit null labels are reviewed.
    assert all(group['counts']['total'] == 0 for group in result['categories'])


def test_same_decision_counts_once_per_game_but_again_in_another_game():
    db = MemoryDatabase()
    db.records += [deepcopy(db.records[0]), {**deepcopy(db.records[0]), 'id': 'game-two'}]
    result = lesson_analytics(db, 'alice')
    assert result['imported_games'] == result['analyzed_games'] == 2
    assert result['analyzed_moves'] == 10 and result['errors']['total'] == 6


def test_scope_ignores_opponent_moves_other_players_stale_games_and_mismatched_evidence():
    db = MemoryDatabase()
    original = db.records[0]
    original['moves']['1'] = saved_move(1, -100)
    original['moves']['2']['fen'] = 'a different position'
    original['moves']['4']['played_move'] = 'a2a3'
    original['moves']['01'] = saved_move(1, -100)
    db.records.append({**deepcopy(original), 'id': 'stale', 'pgn_hash': 'old-pgn'})
    db.records.append({**deepcopy(original), 'id': 'outsider', 'metadata': {'white': 'carol', 'black': 'dave'}})
    result = lesson_analytics(db, 'alice')
    assert result['imported_games'] == 2 and result['analyzed_games'] == 1
    assert result['analyzed_moves'] == 3 and result['errors']['total'] == 1
    assert result['errors']['blunder'] == 1


def test_no_games_and_unanalyzed_games_have_an_empty_breakdown():
    db = MemoryDatabase()
    db.records[0]['moves'] = None
    result = lesson_analytics(db, 'alice')
    assert result['imported_games'] == 1 and result['analyzed_moves'] == result['errors']['total'] == 0
    db.records.clear()
    result = lesson_analytics(db, 'alice')
    assert result['imported_games'] == result['analyzed_games'] == 0
    assert len(result['categories']) == 3


def test_legacy_reviews_keep_severity_totals_but_need_refresh_not_category_remapping():
    db = MemoryDatabase()
    for review in db.feedback.values():
        review.pop('classification_version')
    first = next(iter(db.feedback.values()))
    first['teaching']['move_evaluation']['mistake_classification'] = {'category': 'positional', 'subcategory': 'piece_play'}
    result = lesson_analytics(db, 'alice')
    assert result['errors'] == result['unclassified']
    assert result['outdated_reviews'] == 3 and result['pending_reviews'] == 0
    assert all(group['counts']['total'] == 0 for group in result['categories'])


def test_current_explicit_null_is_reviewed_but_remains_unclassified():
    db = MemoryDatabase()
    db.feedback = {key: feedback(None, None) for key in db.feedback}
    result = lesson_analytics(db, 'alice')
    assert result['unclassified'] == result['errors']
    assert result['outdated_reviews'] == result['pending_reviews'] == 0


def test_version_two_and_enriched_positional_records_keep_existing_lesson_counts():
    db = MemoryDatabase()
    expected = lesson_analytics(db, 'alice')
    for review in db.feedback.values():
        review['classification_version'] = 2
    assert lesson_analytics(db, 'alice') == expected
    positional = next(iter(db.feedback.values()))
    positional['classification_version'] = CLASSIFICATION_VERSION
    positional['teaching']['move_evaluation']['mistake_classification'].update(
        best_move_piece='knight', played_piece='pawn', same_piece=False)
    assert lesson_analytics(db, 'alice') == expected


def test_http_uses_latest_review_per_move_and_selected_profile_without_model_calls(test_db_url):
    db = Database(test_db_url)
    game = normalize_game(raw_game(), 'alice')
    db.save_import('alice', [game], 1)
    db.save_import('bob', [game], 1)
    fingerprint = pgn_fingerprint(game['pgn'])
    for color, ply in [('white', 0), ('black', 1)]:
        db.begin_game_analysis(game['id'], color, fingerprint, 1)
        db.save_game_analysis_move(game['id'], color, fingerprint, ply, saved_move(ply, -100, game['pgn']))
    review = MoveReview.from_game(game['pgn'], 0)
    for number, label in enumerate(['hanging_piece', 'fork'], 1):
        db.save_coach_feedback(CoachAnalysis(text='Saved coaching', model='test', response_id=f'review-{number}',
            position=review.position, played_move=review.played_move_uci, usage=None,
            position_analysis={'classification_version': CLASSIFICATION_VERSION, 'structured': feedback('tactical_miss', label)['teaching']}))
    def forbidden(*args, **kwargs):
        raise AssertionError('Lessons must not start any engine or model work')
    with TestClient(create_app(test_db_url, game_engine=forbidden, coach_factory=forbidden)) as client:
        response = client.get('/api/lessons?username=ALICE')
        assert response.status_code == 200
        result = response.json()
        assert result['errors']['total'] == 1
        rows = {row['key']: row['counts'] for row in category(result, 'tactical_miss')['subcategories']}
        assert rows['fork']['blunder'] == 1 and rows['hanging_piece']['total'] == 0
        black = client.get('/api/lessons?username=bob').json()
        assert black['errors']['total'] == black['unclassified']['total'] == black['pending_reviews'] == 1
        assert client.get('/api/lessons?username=outsider').json()['imported_games'] == 0
        assert client.get('/api/lessons').status_code == 422
        assert client.get('/api/lessons?username=bad%20name').status_code == 422
        assert len(db.coach_feedback_for_reviews([(review.position.fen, review.played_move_uci)])) == 1
