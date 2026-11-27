import test from 'node:test';
import assert from 'node:assert/strict';
import {boardPieceMotions, movePreviewSteps, pieceMotions, piecesAt} from '../src/boardAnimation.ts';
import {boardMoveSound} from '../src/boardSound.ts';
import {replayGame} from './fixtures/replayGame.mjs';

test('replay and variation positions slide forward and backward without animation instructions', () => {
  const {positions, moves} = replayGame;
  for (let index = 0; index < moves.length; index++) {
    const from = moves[index].uci.slice(0, 2), to = moves[index].uci.slice(2, 4);
    assert.deepEqual(boardPieceMotions(positions[index].fen, positions[index + 1].fen), [{from, to}]);
    assert.deepEqual(boardPieceMotions(positions[index + 1].fen, positions[index].fen), [{from: to, to: from}]);
  }
});

test('seeks and returning from variations animate every changed piece once', () => {
  const {positions} = replayGame;
  const motions = boardPieceMotions(positions[0].fen, positions[3].fen);
  assert.deepEqual(motions, [{from: 'e1', to: 'f1'}, {from: 'b8', to: 'b2'}]);
  assert.deepEqual(boardPieceMotions(positions[3].fen, positions[0].fen),
    motions.map(({from, to}) => ({from: to, to: from})));
  const before = '4k3/8/8/8/8/8/8/R3K2R w - - 0 1';
  const after = '4k3/8/8/8/R6R/8/8/4K3 w - - 0 5';
  assert.deepEqual(boardPieceMotions(before, after), [{from: 'a1', to: 'a4'}, {from: 'h1', to: 'h4'}]);
});

test('automatic motion covers captures, en passant, promotions and their undo', () => {
  for (const [before, after, from, to] of [
    ['4k3/8/8/3p4/4P3/8/8/4K3 w - - 0 1', '4k3/8/8/3P4/8/8/8/4K3 b - - 0 1', 'e4', 'd5'],
    ['4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1', '4k3/8/3P4/8/8/8/8/4K3 b - - 0 1', 'e5', 'd6'],
    ...['Q', 'R', 'B', 'N'].map(piece => [
      '1r2k3/P7/8/8/8/8/8/4K3 w - - 0 1', `1${piece}2k3/8/8/8/8/8/8/4K3 b - - 0 1`, 'a7', 'b8',
    ]),
    ...['q', 'r', 'b', 'n'].map(piece => [
      '4k3/8/8/8/8/8/7p/4K3 b - - 0 1', `4k3/8/8/8/8/8/8/4K2${piece} w - - 0 2`, 'h2', 'h1',
    ]),
  ]) {
    assert.deepEqual(boardPieceMotions(before, after), [{from, to}]);
    assert.deepEqual(boardPieceMotions(after, before), [{from: to, to: from}]);
  }
});

test('automatic castling slides both king and rook in both directions', () => {
  for (const [before, after, expected] of [
    ['4k3/8/8/8/8/8/8/4K2R w K - 0 1', '4k3/8/8/8/8/8/8/5RK1 b - - 1 1', [{from: 'e1', to: 'g1'}, {from: 'h1', to: 'f1'}]],
    ['r3k3/8/8/8/8/8/8/4K3 b q - 0 1', '2kr4/8/8/8/8/8/8/4K3 w - - 1 2', [{from: 'e8', to: 'c8'}, {from: 'a8', to: 'd8'}]],
  ]) {
    assert.deepEqual(new Set(boardPieceMotions(before, after)), new Set(expected));
    assert.deepEqual(new Set(boardPieceMotions(after, before)), new Set(expected.map(({from, to}) => ({from: to, to: from}))));
  }
});

test('preview hints cannot move stationary pieces or omit other changes', () => {
  const {positions} = replayGame;
  assert.deepEqual(boardPieceMotions(positions[0].fen, positions[3].fen, {uci: 'b8b2', reverse: false}),
    [{from: 'b8', to: 'b2'}, {from: 'e1', to: 'f1'}]);
  // A stale move hint must not slide a queen into a king's square.
  assert.deepEqual(boardPieceMotions(positions[0].fen, positions[1].fen, {uci: 'b8e8', reverse: false}), [{from: 'b8', to: 'b4'}]);
  assert.deepEqual(boardPieceMotions(positions[1].fen, positions[1].fen, {uci: 'b8b4', reverse: false}), []);
  assert.deepEqual(boardPieceMotions(positions[1].fen, positions[1].fen.replace(' w ', ' b ')), []);
});

test('alternative selection undoes Re1 before moving the queen to d2 and can switch or return', () => {
  const position = fen => ({fen, last_move: null, check_square: null});
  const decision = position('4k3/8/8/8/8/8/8/3Q1RK1 w - - 0 14');
  const original = position('4k3/8/8/8/8/8/8/3QR1K1 b - - 1 14');
  const queen = position('4k3/8/8/8/8/8/3Q4/5RK1 b - - 1 14');
  const king = position('4k3/8/8/8/8/8/8/3Q1R1K b - - 1 14');
  for (const [current, target, uci, undo] of [
    [original, queen, 'd1d2', 'f1e1'], [queen, king, 'g1h1', 'd1d2'], [queen, original, 'f1e1', 'd1d2'],
  ]) {
    const steps = movePreviewSteps(decision, current, target, uci, undo);
    assert.deepEqual(steps.map(step => step.position), [decision, target]);
    let before = current;
    for (const {position, animation} of steps) {
      assert.equal(pieceMotions(before.fen, position.fen, animation.uci, animation.reverse).length, 1);
      before = position;
    }
  }
  // A click while the previous move is being undone starts from that decision.
  assert.equal(movePreviewSteps(decision, decision, king, 'g1h1', 'd1d2').length, 1);
  // Collapsing the original move's explanation should leave its piece still.
  assert.deepEqual(movePreviewSteps(decision, original, original, 'f1e1', 'f1e1'), [{position: original}]);
});

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
