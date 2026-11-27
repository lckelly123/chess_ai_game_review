import test from 'node:test';
import assert from 'node:assert/strict';
import { coachMoves } from '../src/coachMoves.ts';
import { visibleCandidate } from '../src/boardAnnotations.ts';

const candidate = {uci: 'e2e4', reason: 'Control the center.'};
const engineMove = (uci, san, cp) => ({uci, san, depth: 12, score: {cp, mate: null, bound: 'exact'}});
const response = {
  fen: 'current-fen', response_id: 'new', played_move: 'd2d4',
  teaching: {candidate_moves: [candidate], move_evaluation: {explanation: 'Another sound central move.'}},
  candidate_san: {e2e4: 'e4'},
  stockfish: {perspective: 'White', played_move: engineMove('d2d4', 'd4', 30)},
  position_evidence: {top_moves: [engineMove('e2e4', 'e4', 50)]},
};

test('played move joins the move list with its own score and explanation without changing recommendations', () => {
  const before = structuredClone(response);
  const rows = coachMoves(response);
  assert.deepEqual(rows.map(move => move.uci), ['e2e4', 'd2d4']);
  assert.deepEqual(rows.map(move => move.engineMove.score.cp), [50, 30]);
  assert.equal(rows[1].reason, 'Another sound central move.');
  assert.equal(rows[1].isPlayed, true);
  assert.equal(rows[1].san, 'd4');
  assert.deepEqual(response, before);
});

test('recommended player move appears once, retaining its explanation', () => {
  const matching = {...response, played_move: 'e2e4', stockfish: {...response.stockfish, played_move: engineMove('e2e4', 'e4', 45)},
    teaching: {...response.teaching, move_evaluation: {explanation: null}}};
  const rows = coachMoves(matching);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].isPlayed, true);
  assert.equal(rows[0].reason, candidate.reason);
  assert.equal(rows[0].feedback, undefined);
  assert.equal(rows[0].engineMove.score.cp, 45);
});

test('missing candidate evidence never borrows the played move score', () => {
  const rows = coachMoves({...response, position_evidence: null});
  assert.equal(rows[0].engineMove, undefined);
  assert.equal(rows[1].engineMove.score.cp, 30);
  assert.equal(coachMoves({...response, played_move: null}).length, 1);
  assert.deepEqual(coachMoves(), []);
});

test('player move board previews support promotion and obey position and run guards', () => {
  const promoted = {...response, played_move: 'a7a8q', teaching: {...response.teaching, candidate_moves: []}};
  const selection = {fen: promoted.fen, responseId: promoted.response_id, uci: promoted.played_move};
  const annotation = visibleCandidate(selection, promoted, promoted.fen, false);
  assert.equal(annotation.uci, 'a7a8q');
  assert.equal(visibleCandidate(selection, promoted, promoted.fen, true), undefined);
  assert.equal(visibleCandidate(selection, promoted, 'other-fen', false), undefined);
  assert.equal(visibleCandidate({...selection, responseId: 'old'}, promoted, promoted.fen, false), undefined);
});
