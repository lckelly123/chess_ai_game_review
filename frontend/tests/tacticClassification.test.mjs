import test from 'node:test';
import assert from 'node:assert/strict';
import { tacticSummary } from '../src/tacticClassification.ts';

const line = (direction, motifs, coverage = 'bounded') => ({direction, motifs, coverage});
const result = {version: 1, fen: 'position', played_move: 'e2e4', status: 'classified',
  lines: [line('missed', ['fork']), line('allowed', ['pin', 'double_check'])]};
const review = {fen: 'position', played_move: 'e2e4', stockfish: {tactic_classification: result}};

test('engine-only reviews display both directions and all supported motifs', () => {
  assert.equal(tacticSummary(undefined, review), 'Missed: fork · Allowed: pin, double check');
});

test('old coach feedback can use matching newly saved ingestion results', () => {
  assert.equal(tacticSummary({fen: 'position', played_move: 'e2e4'}, review), tacticSummary(undefined, review));
  assert.equal(tacticSummary({fen: 'different', played_move: 'e2e4'}, review), 'Not yet analysed');
  assert.equal(tacticSummary({fen: 'position', played_move: 'd2d4'}, review), 'Not yet analysed');
  assert.equal(tacticSummary({fen: 'position', played_move: null}), null);
});

test('partial, no-match, skipped and missing evidence remain distinct', () => {
  const summary = changes => tacticSummary(undefined, {...review, stockfish: {tactic_classification: {...result, ...changes}}});
  assert.equal(summary({lines: [line('missed', ['fork'], 'insufficient')]}), 'Missed: fork · Partial line evidence');
  assert.equal(summary({status: 'unclassified', lines: []}), 'No supported motif found');
  assert.equal(summary({status: 'insufficient_evidence', lines: []}), 'Insufficient line evidence');
  assert.equal(summary({status: 'not_applicable', lines: []}), 'No error to classify');
  assert.equal(summary({version: 0}), 'Not yet analysed');
});
