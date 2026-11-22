import test from 'node:test';
import assert from 'node:assert/strict';
import { positionDecision } from '../src/positionDecision.ts';

for (const [tag, score] of [['forgiving', 0], ['flexible', 20.001], ['selective', 50], ['demanding', 70], ['critical', 100]]) {
  test(`renders ${tag} using backend classification and includes its score in the accessible description`, () => {
    const result = positionDecision({decision_classification: tag, unclassified_reason: null, sharpness: {version: 1, score}});
    assert.equal(result.label.toLowerCase(), tag);
    assert.equal(result.className, tag);
    assert.ok(result.tooltip.includes(`${score.toFixed(2)}/100`));
    assert.ok(result.tooltip.includes('top five'));
  });
}

test('all short-position reasons have neutral labels and never show an invented score', () => {
  for (const [reason, label] of [['terminal_position', 'Game over'], ['single_legal_move', 'Only legal move'],
      ['fewer_than_five_legal_moves', 'Unclassified'], ['insufficient_engine_evidence', 'Unclassified']]) {
    const result = positionDecision({decision_classification: null, unclassified_reason: reason, sharpness: {version: 1, score: null}});
    assert.equal(result.label, label);
    assert.equal(result.className, 'unclassified');
    assert.equal(result.tooltip.includes('/100'), false);
  }
});

test('legacy, unsupported and invalid labels cannot masquerade as new sharpness', () => {
  assert.equal(positionDecision(), undefined);
  for (const evidence of [
    {decision_classification: 'flexible'},
    {decision_classification: 'clear_preference', sharpness: {version: 1, score: 50}},
    {decision_classification: 'critical', sharpness: {version: 0, score: 100}},
    {decision_classification: 'critical', sharpness: {version: 1, score: NaN}},
    {decision_classification: 'critical', sharpness: {version: 1, score: 101}},
  ]) assert.equal(positionDecision(evidence).label, 'Unclassified');
});
