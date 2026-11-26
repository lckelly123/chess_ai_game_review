import asyncio

import chess
import pytest

from backend.chess_games import parse_game, replay
from backend.game_analysis import GameAnalysisService, analyze_final_position
from backend.game_phase import mixedness, next_phase
from backend.game_statistics import build_statistics, game_accuracy, position_evaluation, terminal_evaluation


@pytest.mark.parametrize('cps,start,white,black', [
    ([15, 15, 15], 'white', 100, 100),
    ([15, -900, -900], 'white', 10.66405689619949, 100),
    ([15, 15, 900], 'white', 100, 12.303138647232768),
    ([15, -900, 0], 'white', 10.66405689619949, 11.45897404122671),
    ([15] * 21 + [-900], 'white', 46.85340283303506, 100),
    ([1000, -1000, -1000], 'white', 0.5, 100),
    ([15, 900, 900], 'black', 100, 12.303138647232768),
    ([15, -300, -245, -210, -175, -140, 450, -70, -300, 0, 35, 450, 105, 140, 175, -300,
      450, 280, 315, 350, 385, 450, -300, 490, 525, 560, 450, 630, 665, -300, 735, 450, 805],
     'white', 45.003716172548046, 45.01014589516745),
])
def test_lichess_accuracy_regression(cps, start, white, black):
    assert game_accuracy(cps, start) == pytest.approx({'white': white, 'black': black})


def test_accuracy_requires_moves_from_both_players():
    assert game_accuracy([15, 15], 'white') == {'white': None, 'black': None}


def test_root_evaluation_normalizes_black_without_using_played_score():
    board = chess.Board()
    board.push_uci('e2e4')
    evidence = {'perspective': 'Black', 'top_moves': [{'depth': 18, 'score': {'cp': -45, 'mate': None, 'bound': 'exact'}}],
                'played_move': {'score': {'cp': -900, 'mate': None, 'bound': 'exact'}}}
    assert position_evaluation(evidence, 1, board.fen())['cp'] == 45
    evidence['top_moves'][0]['score'] = {'cp': None, 'mate': 3, 'bound': 'exact'}
    point = position_evaluation(evidence, 1, board.fen())
    assert point['mate'] == -3 and point['mate_winner'] == 'black'
    evidence['top_moves'][0]['score']['bound'] = 'lower'
    assert position_evaluation(evidence, 1, board.fen()) is None


def test_terminal_mate_zero_keeps_winning_side_and_draw_is_zero():
    for pgn, winner in [('1. f3 e5 2. g4 Qh4# 0-1', 'black'), ('1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0', 'white')]:
        final = analyze_final_position(pgn)
        assert final['status'] == 'terminal' and final['mate'] == 0 and final['mate_winner'] == winner
    board = chess.Board('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1')
    assert terminal_evaluation(board, 5)['cp'] == 0
    assert terminal_evaluation(parse_game('1. e4 1-0').end().board(), 1) is None
    claimed = analyze_final_position('1. Nf3 Nf6 2. Ng1 Ng8 3. Nf3 Nf6 4. Ng1 Ng8 1/2-1/2')
    assert claimed['status'] == 'terminal' and claimed['cp'] == 0
    assert claimed['termination'] == 'threefold_repetition'


def test_missing_positions_are_not_removed_or_replaced_by_zero():
    detail = replay('1. e4 e5 *')
    final = {'ply': 2, 'fen': detail['positions'][2]['fen'], 'status': 'evaluated', 'cp': 20, 'mate': None}
    stats = build_statistics(detail, {}, final)
    assert [point['ply'] for point in stats['timeline']] == [0, 1, 2]
    assert not stats['complete'] and stats['accuracy'] == {'white': None, 'black': None}


def test_lichess_phases_and_irreversible_transitions():
    start = chess.Board()
    assert next_phase(start) == 'opening'
    middle = chess.Board('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/R2QK2R w KQkq - 0 1')
    end = chess.Board('r2qk2r/pppppppp/8/8/8/8/PPPPPPPP/R2QK2R w KQkq - 0 1')
    assert next_phase(middle) == 'middlegame'
    assert next_phase(end) == 'endgame'
    assert next_phase(start, 'middlegame') == 'middlegame'
    assert next_phase(start, 'endgame') == 'endgame'
    developed = chess.Board('rnbqkbnr/pppppppp/8/8/3Q4/2N1BN2/PPPPPPPP/R3KB1R w KQkq - 0 1')
    developed.remove_piece_at(chess.F1)
    developed.set_piece_at(chess.C4, chess.Piece(chess.BISHOP, chess.WHITE))
    assert (developed.occupied & ~(developed.kings | developed.pawns)).bit_count() > 10
    assert next_phase(developed) == 'middlegame'
    assert mixedness(start) <= 150
    # Intermixed pawns trigger middlegame while home ranks and all pieces remain.
    mixed = chess.Board('rnbqkbnr/8/8/P1P1P1P1/1p1p1p1p/P1P1P1P1/1p1p1p1p/RNBQKBNR w KQkq - 0 1')
    assert mixedness(mixed) > 150 and next_phase(mixed) == 'middlegame'


def test_replay_phases_match_shown_board_and_timing_uses_movers_own_clock():
    detail = replay('[TimeControl "300+2"]\n\n1. e4 {[%clk 0:04:58]} e5 {[%clk 0:05:01]} 2. Nf3 {[%clk 0:04:50]} Nc6 {[%emt 0:00:07]} *')
    assert [move['elapsed_seconds'] for move in detail['moves']] == [4, 1, 10, 7]
    assert all(position['phase'] == 'opening' for position in detail['positions'])
    missing = replay('[TimeControl "300+2"]\n\n1. e4 e5 2. Nf3 {[%clk 0:04:50]} Nc6 *')
    assert all(move['elapsed_seconds'] is None for move in missing['moves'])
    custom = replay('[SetUp "1"]\n[FEN "8/7k/8/8/8/8/P7/K7 b - - 0 23"]\n[TimeControl "300+2"]\n\n23... Kg6 {[%clk 0:03:00]} 24. a4 *')
    assert custom['moves'][0]['elapsed_seconds'] is None
    assert custom['positions'][0]['phase'] == 'endgame'


def test_final_search_failure_resumes_without_repeating_moves_and_is_shared_between_players(monkeypatch):
    from backend.tests.test_game_analysis import MemoryDatabase, evidence, fake_coach, finish
    from backend.tests.position_fixtures import position_evidence
    db, calls, finals = MemoryDatabase(), [], []
    def engine(review):
        calls.append(review.played_move_uci)
        return evidence(review)
    def final(pgn):
        finals.append(pgn)
        if len(finals) == 1:
            raise TimeoutError('retry')
        detail = replay(pgn)
        fen = detail['positions'][-1]['fen']
        return position_evaluation(position_evidence(fen), len(detail['moves']), fen)
    async def run():
        service = GameAnalysisService(db, set(), engine, final_analyzer=final, coach_factory=fake_coach)
        await service.start(db.record['id'], 'alice')
        await finish(service)
        assert (await service.saved(db.record['id'], 'alice'))['status'] == 'failed'
        await service.start(db.record['id'], 'alice')
        await finish(service)
        saved = await service.saved(db.record['id'], 'alice')
        assert saved['statistics']['complete'] and len(saved['statistics']['timeline']) == 8
        assert len(calls) == 7 and len(finals) == 2
        await service.start(db.record['id'], 'bob')
        await finish(service)
        assert len(calls) == 7 and len(finals) == 2
        # A legacy completed review gains statistics using its saved searches.
        db.rows[(db.record['id'], 'white')]['statistics'] = None
        await service.start(db.record['id'], 'alice')
        await finish(service)
        assert (await service.saved(db.record['id'], 'alice'))['statistics']['complete']
        assert len(calls) == 7 and len(finals) == 2
    asyncio.run(run())
