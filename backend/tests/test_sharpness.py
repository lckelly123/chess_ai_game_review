from copy import deepcopy
from datetime import datetime, timezone
import math

import chess
import pytest

from backend.coach.sharpness import (
    A_CP, CUTOFF_CP, WEIGHTS, SHARPNESS_VERSION,
    normalized_sharpness, sharpness_tag, with_position_sharpness,
)
from backend.coach.routes import AnalyzePositionResponse
from backend.coach.classification import CLASSIFICATION_VERSION
from backend.coach.responses import build_request
from backend.tests.position_fixtures import position_evidence


def scored(values):
    evidence = position_evidence(chess.STARTING_FEN)
    for candidate, value in zip(evidence['top_moves'], values):
        candidate['score'] = {'cp': value if isinstance(value, int) else None,
                              'mate': int(value[1:]) if isinstance(value, str) else None, 'bound': 'exact'}
    return evidence


@pytest.mark.parametrize('boundary,lower,upper', [(20, 'forgiving', 'flexible'), (40, 'flexible', 'selective'),
    (60, 'selective', 'demanding'), (80, 'demanding', 'critical')])
def test_unrounded_inclusive_tag_boundaries(boundary, lower, upper):
    assert sharpness_tag(boundary) == lower
    assert sharpness_tag(math.nextafter(boundary, math.inf)) == upper
    assert sharpness_tag(boundary + .001) == upper


def test_normalization_reference_points_and_units():
    assert normalized_sharpness(0) == 0
    assert normalized_sharpness(CUTOFF_CP) == normalized_sharpness(3000) == 100
    assert normalized_sharpness(24.358050186231925) == pytest.approx(29.074210709831565)
    assert sharpness_tag(0) == 'forgiving' and sharpness_tag(100) == 'critical'
    for value in [-1, math.inf, math.nan]:
        with pytest.raises(ValueError):
            normalized_sharpness(value)


def test_database_example_uses_all_five_cp_even_with_equal_wdl():
    original = scored([656, 461, 442, 437, 412])
    for c in original['top_moves']:
        c['wdl'] = {'wins': 1000, 'draws': 0, 'losses': 0}
    snapshot = deepcopy(original)
    result = with_position_sharpness(original)
    expected = .6439142598879724 * 195 + .23688281808991013 * 19 + .08714431874203257 * 5 + .03205860328008499 * 25
    assert result['sharpness']['raw_cp'] == pytest.approx(expected)
    assert result['sharpness']['score'] == pytest.approx(normalized_sharpness(expected))
    assert result['decision_classification'] == 'demanding'
    assert original == snapshot
    changed = scored([656, 461, 442, 437, -100])
    assert with_position_sharpness(changed)['sharpness']['raw_cp'] > expected


@pytest.mark.parametrize('values,effective', [
    ([5000, 3000, 2500, 2200, 2100], [1000] * 5),
    ([-2100, -2200, -2500, -3000, -5000], [-1000] * 5),
    ([1800, 1500, 1250, 1100, 1001], [1000] * 5),
    ([-1001, -1100, -1250, -1500, -1800], [-1000] * 5),
    ([1001, 1000, 0, -1000, -1001], [1000, 1000, 0, -1000, -1000]),
    ([1000, 999, 0, -999, -1000], [1000, 999, 0, -999, -1000]),
    (['M3', 'M5', 'M7', 'M9', 'M11'], [1000] * 5),
    (['M-11', 'M-9', 'M-7', 'M-5', 'M-3'], [-1000] * 5),
    (['M1', 800, 0, -800, 'M-1'], [1000, 800, 0, -800, -1000]),
    (['M1', 'M-10', 'M-9', 'M-8', 'M-1'], [1000, -1000, -1000, -1000, -1000]),
])
def test_cap_and_mate_policy_include_best_and_preserve_raw_scores(values, effective):
    original = scored(values)
    result = with_position_sharpness(original)
    assert result['sharpness']['cap_cp'] == 1000
    assert result['sharpness']['capped_scores_cp'] == effective
    assert result['top_moves'] == original['top_moves']
    expected = sum(w * (effective[i] - effective[i+1]) for i, w in enumerate(WEIGHTS))
    assert result['sharpness']['raw_cp'] == pytest.approx(expected)
    assert result['sharpness']['score'] == normalized_sharpness(expected)


def test_scores_are_sorted_without_changing_engine_rank_or_candidate_order():
    original = scored([0, 100, -100, 50, -50])
    result = with_position_sharpness(original)
    assert result['sharpness']['capped_scores_cp'] == [100, 50, 0, -50, -100]
    assert result['top_moves'] == original['top_moves']
    assert result['sharpness']['raw_cp'] == pytest.approx(50)


@pytest.mark.parametrize('count,fen', [
    (0, '7k/6Q1/5K2/8/8/8/8/8 b - - 0 1'),
    (1, '7k/8/6K1/8/8/8/8/R7 b - - 0 1'),
    (2, '7k/8/5K2/8/8/8/8/R7 b - - 0 1'),
    (3, '7k/8/8/8/8/8/8/KR6 b - - 0 1'),
    (4, '6k1/8/4K3/8/8/8/8/R7 b - - 0 1'),
])
def test_legal_count_comes_from_board_not_cached_metadata(count, fen):
    board = chess.Board(fen)
    assert board.is_valid() and board.legal_moves.count() == count
    evidence = position_evidence(fen)
    evidence['legal_move_count'] = 99
    evidence['decision_classification'] = 'critical'
    result = with_position_sharpness(evidence)
    assert result['sharpness']['score'] is None and result['decision_classification'] is None
    assert result['unclassified_reason'] == ('terminal_position' if count == 0 else 'single_legal_move' if count == 1 else 'fewer_than_five_legal_moves')


@pytest.mark.parametrize('defect', ['missing', 'duplicate', 'bound', 'depth', 'score', 'perspective', 'rank', 'illegal'])
def test_incomplete_saved_evidence_never_inherits_legacy_label(defect):
    e = scored([500, 100, 0, -100, -200])
    e['decision_classification'] = 'clear_preference'
    if defect == 'missing': e['top_moves'].pop()
    if defect == 'duplicate': e['top_moves'][1]['uci'] = e['top_moves'][0]['uci']
    if defect == 'bound': e['top_moves'][1]['score']['bound'] = 'upper'
    if defect == 'depth': e['top_moves'][1]['depth'] += 1
    if defect == 'score': e['top_moves'][1]['score']['cp'] = None
    if defect == 'perspective': e['perspective'] = 'Black'
    if defect == 'rank': e['top_moves'][1]['rank'] = 1
    if defect == 'illegal': e['top_moves'][1]['uci'] = 'e2e5'
    result = with_position_sharpness(e)
    assert result['sharpness']['score'] is None
    assert result['decision_classification'] is None
    assert result['unclassified_reason'] == 'insufficient_engine_evidence'


@pytest.mark.parametrize('saved_version', [None, 1])
def test_api_rescores_old_evidence_without_marking_old_coaching_current(saved_version):
    old = scored([1800, 1500, 1250, 1100, 1001])
    if saved_version is None:
        old.pop('sharpness')
    else:
        raw = sum(w * gap for w, gap in zip(WEIGHTS, [300, 250, 150, 99]))
        old['sharpness'].update(version=1, cap_cp=2000, raw_cp=raw, score=normalized_sharpness(raw),
                                capped_scores_cp=[1800, 1500, 1250, 1100, 1001])
    old.update(classification='Demanding', decision_classification='demanding')
    snapshot = deepcopy(old)
    response = AnalyzePositionResponse(fen=chess.STARTING_FEN, text='Saved explanation', model='model',
        response_id='saved', created_at=datetime.now(timezone.utc), position_evidence=old,
        classification_version=CLASSIFICATION_VERSION, sharpness_version=saved_version)
    result = response.model_dump()
    assert result['position_evidence']['sharpness']['version'] == SHARPNESS_VERSION
    assert result['position_evidence']['sharpness']['cap_cp'] == 1000
    assert result['position_evidence']['sharpness']['score'] == 0
    assert result['position_evidence']['decision_classification'] == 'forgiving'
    assert result['sharpness_current'] is False and result['classification_current'] is True
    assert result['text'] == 'Saved explanation' and old == snapshot


def test_compact_prompt_receives_recalculated_label_without_formula_metadata():
    evidence = scored([656, 461, 442, 437, 412])
    evidence['decision_classification'] = 'clear_preference'
    request = build_request(chess.STARTING_FEN, evidence=evidence)
    content = request['input'][1]['content']
    assert "Decision mode: demanding" in content
    assert "cap_cp" not in content
    assert "a_cp" not in content and "cutoff_cp" not in content
    assert "move_quality_policy" not in content
    assert 'clear_preference' not in content
    assert A_CP == 10
