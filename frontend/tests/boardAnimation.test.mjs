import test from 'node:test';
import assert from 'node:assert/strict';
import {pieceMotions, piecesAt} from '../src/boardAnimation.ts';
import {boardMoveSound} from '../src/boardSound.ts';

test('undo and replay animate in the proper direction and each board change has a sound', () => {
  const before = '1q2k3/8/8/8/8/8/8/4K3 b - - 0 12';
  const better = '4k3/8/8/8/8/8/1q6/4K3 w - - 1 13';
  const original = '4k3/8/8/8/1q6/8/8/4K3 w - - 1 13';
  assert.deepEqual(pieceMotions(better, before, 'b8b2', true), [{from: 'b2', to: 'b8'}]);
  assert.deepEqual(pieceMotions(before, original, 'b8b4'), [{from: 'b8', to: 'b4'}]);
  assert.equal(boardMoveSound(better, before), 'move');
  assert.equal(boardMoveSound(before, original), 'move');
  assert.deepEqual(pieceMotions(original, original, 'b8b4'), []);
  assert.deepEqual(pieceMotions(before, original, 'b8b2'), []);
});

test('castling animates both pieces forward and backward', () => {
  for (const [before, after, uci, rook] of [
    ['4k3/8/8/8/8/8/8/4K2R w K - 0 1', '4k3/8/8/8/8/8/8/5RK1 b - - 1 1', 'e1g1', {from: 'h1', to: 'f1'}],
    ['r3k3/8/8/8/8/8/8/4K3 b q - 0 1', '2kr4/8/8/8/8/8/8/4K3 w - - 1 2', 'e8c8', {from: 'a8', to: 'd8'}],
  ]) {
    const forward = [{from: uci.slice(0, 2), to: uci.slice(2, 4)}, rook];
    assert.deepEqual(pieceMotions(before, after, uci), forward);
    assert.deepEqual(pieceMotions(after, before, uci, true), forward.map(({from, to}) => ({from: to, to: from})));
  }
});

test('capture, en passant and promotion restore the exact position and retain capture or move sound on undo', () => {
  for (const [before, after, uci, sound] of [
    ['4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1', '4k3/8/8/3P4/8/8/8/4K3 b - - 0 1', 'e4d5', 'capture'],
    ['4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1', '4k3/8/3P4/8/8/8/8/4K3 b - - 0 1', 'e5d6', 'capture'],
    ['4k3/P7/8/8/8/8/8/4K3 w - - 0 1', 'N3k3/8/8/8/8/8/8/4K3 b - - 0 1', 'a7a8n', 'move'],
  ]) {
    assert.deepEqual(pieceMotions(after, before, uci, true), [{from: uci.slice(2, 4), to: uci.slice(0, 2)}]);
    assert.equal(piecesAt(before)[uci.slice(0, 2)], 'P');
    assert.equal(boardMoveSound(after, before), sound);
  }
});
