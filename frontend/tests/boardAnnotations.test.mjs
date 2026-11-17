import test from 'node:test';
import assert from 'node:assert/strict';
import { squareCenter, visibleCandidate } from '../src/boardAnnotations.ts';

test('square centers follow either board orientation, including castling and promotion endpoints', () => {
  assert.deepEqual(squareCenter('a8', false), [.5, .5]);
  assert.deepEqual(squareCenter('h1', false), [7.5, 7.5]);
  assert.deepEqual(squareCenter('a8', true), [7.5, 7.5]);
  assert.deepEqual(squareCenter('h1', true), [.5, .5]);
  assert.deepEqual(squareCenter('e1', true), [3.5, .5]);
  assert.deepEqual(squareCenter('g1', true), [1.5, .5]);
  assert.deepEqual(squareCenter('a7', false), [.5, 1.5]);
});

test('candidate overlays never leak across positions, runs, or replay transitions', () => {
  const candidate = { uci: 'g1f3', highlight_squares: ['f3', 'e5'], reason: 'Control the center.' };
  const response = { fen: 'current-fen', response_id: 'new-run', teaching: { candidate_moves: [candidate] } };
  const selection = { fen: response.fen, responseId: response.response_id, uci: candidate.uci };
  assert.equal(visibleCandidate(selection, response, response.fen, false), candidate);
  assert.equal(visibleCandidate(selection, response, response.fen, true), undefined);
  assert.equal(visibleCandidate(selection, response, 'next-fen', false), undefined);
  assert.equal(visibleCandidate({ ...selection, responseId: 'old-run' }, response, response.fen, false), undefined);
  assert.equal(visibleCandidate({ ...selection, uci: 'e2e4' }, response, response.fen, false), undefined);
  assert.equal(visibleCandidate(null, response, response.fen, false), undefined);
  assert.equal(visibleCandidate(selection, { ...response, teaching: null }, response.fen, false), undefined);
  assert.equal(visibleCandidate(selection, { ...response, teaching: { candidate_moves: [] } }, response.fen, false), undefined);
});
