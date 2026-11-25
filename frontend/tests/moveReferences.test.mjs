import test from 'node:test';
import assert from 'node:assert/strict';
import { moveReferences } from '../src/moveReferences.ts';
import { coachMoves } from '../src/coachMoves.ts';

test('move links use backend SAN and resolve repeated references to the same move', () => {
  const moves = [{uci: 'e1g1', san: 'O-O'}, {uci: 'a7a8n', san: 'a8=N+'}];
  const parts = moveReferences('Choose [[e1g1]] or [[a7a8n]]. [[e1g1]] shelters the king.', moves);
  assert.equal(parts.map(part => part.text).join(''), 'Choose O-O or a8=N+. O-O shelters the king.');
  assert.equal(parts[1].move, parts[5].move);
});

test('unsupported, malformed, and continuation tokens never become clickable moves', () => {
  const text = '<script>text</script> [[e7e5]] [[Nf3]] [[e2e4q]]';
  const parts = moveReferences(text, [{uci: 'e2e4', san: 'e4'}]);
  assert.equal(parts.map(part => part.text).join(''), text);
  assert.ok(parts.every(part => !part.move));
});

test('a candidate that is also the original move retains its separate error assessment', () => {
  const response = {played_move: 'e2e4', candidate_san: {e2e4: 'e4'}, teaching: {
    candidate_moves: [{uci: 'e2e4', reason: 'The candidate mechanism.', highlight_squares: ['e4', 'd5']}],
    move_evaluation: {explanation: 'The original move assessment.'},
  }};
  const rows = coachMoves(response);
  const links = moveReferences('Consider [[e2e4]].', rows).filter(part => part.move);
  assert.equal(rows.length, 1);
  assert.equal(links[0].move.reason, 'The candidate mechanism.');
  assert.equal(links[0].move.feedback, 'The original move assessment.');
});
