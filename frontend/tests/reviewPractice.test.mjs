import test from 'node:test';
import assert from 'node:assert/strict';
import { needsPractice, practiceComplete, practiceKey, restoreAttempts, resultMatches } from '../src/reviewPractice.ts';

const move = {uci: 'e2e4', color: 'white'};
const engine = status => ({fen: 'position', played_move: move.uci, stockfish: {move_quality: {status}}});

test('only the player’s flagged moves enter practice, from matching saved engine or coach evidence', () => {
  for (const quality of ['inaccuracy', 'mistake', 'blunder']) {
    assert.equal(needsPractice(move, 'white', 'position', engine(quality)), true);
    assert.equal(needsPractice(move, 'white', 'position', undefined, engine(quality)), true);
  }
  for (const quality of ['good', 'uncertain']) assert.equal(needsPractice(move, 'white', 'position', engine(quality)), false);
  assert.equal(needsPractice(move, 'black', 'position', engine('blunder')), false);
  assert.equal(needsPractice(move, 'white', 'different', engine('blunder')), false);
  assert.equal(needsPractice(move, 'white', 'position', {...engine('blunder'), played_move: 'd2d4'}), false);
  assert.equal(needsPractice(undefined, 'white', 'position', engine('blunder')), false);
});

test('ordered attempts survive restoration and only a graded Good move is terminal', () => {
  const attempts = ['inaccuracy', 'mistake', 'blunder', 'uncertain'].map(quality => ({uci: 'e2e4', san: 'e4', at: 'now', quality, lossPp: null, status: 'graded'}));
  assert.equal(practiceComplete(attempts), false);
  assert.deepEqual(restoreAttempts(JSON.stringify(attempts)), attempts);
  const good = {...attempts[0], quality: 'good', uci: 'g1f3', san: 'Nf3'};
  assert.equal(practiceComplete([...attempts, good]), true);
  assert.equal(restoreAttempts(JSON.stringify([...attempts, good])).at(-1).uci, 'g1f3');
  assert.equal(practiceComplete([{...good, status: 'checking'}]), false);
  assert.equal(practiceComplete([{...good, status: 'error'}]), false);
});

test('interrupted checks restore as ungraded attempts and corrupt storage is safe', () => {
  const checking = {uci: 'a7a8n', san: 'a8=N', at: 'now', quality: null, lossPp: null, status: 'checking'};
  assert.equal(restoreAttempts(JSON.stringify([checking]))[0].status, 'error');
  assert.equal(practiceComplete(restoreAttempts(JSON.stringify([checking]))), false);
  for (const raw of ['', '{', '{}', '[null, {}]']) assert.deepEqual(restoreAttempts(raw), []);
});

test('practice identities isolate players, games, plies, exact positions and original moves', () => {
  const base = ['game', 'white', 0, 'fen', 'e2e4'];
  const keys = new Set([practiceKey(...base), ...base.map((_, index) => practiceKey(...base.map((value, i) => i === index ? `${value}-other` : value)))]);
  assert.equal(keys.size, 6);
});

test('stale replies and incorrect terminal flags cannot unlock coaching', () => {
  const result = {fen: 'fen', original_move: 'e2e4', move: 'd2d4', accepted: true, quality: {status: 'good'}};
  assert.equal(resultMatches(result, 'fen', 'e2e4', 'd2d4'), true);
  assert.equal(resultMatches(result, 'other', 'e2e4', 'd2d4'), false);
  assert.equal(resultMatches(result, 'fen', 'g1f3', 'd2d4'), false);
  assert.equal(resultMatches(result, 'fen', 'e2e4', 'g1f3'), false);
  assert.equal(resultMatches({...result, quality: {status: 'inaccuracy'}}, 'fen', 'e2e4', 'd2d4'), false);
});
