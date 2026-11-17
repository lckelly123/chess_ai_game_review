import test from 'node:test';
import assert from 'node:assert/strict';
import { playerTurnStops, restoreReplay, replayNavigation } from '../src/replayNavigation.ts';

const positions = (plies, startingWhite = true) => Array.from({ length: plies + 1 }, (_, ply) => ({
  fen: `8/8/8/8/8/8/8/8 ${(ply % 2 === 0) === startingWhite ? 'w' : 'b'} - - 0 1`,
  last_move: null, check_square: null,
}));
const start = (isWhite, plies = 8) => restoreReplay(playerTurnStops(positions(plies), isWhite), 0);
const step = (state, direction = 1, extra = {}) => replayNavigation(state, { type: 'step', direction, animate: true, ...extra });
const settle = state => state.transition ? replayNavigation(state, { type: 'settle', transition: state.transition }) : state;

test('White advances two half-moves, previewing the opponent turn without changing coach position', () => {
  const preview = step(start(true));
  assert.equal(preview.ply, 0);
  assert.deepEqual(preview.transition, { via: 1, to: 2 });
  assert.equal(settle(preview).ply, 2);
  assert.equal(settle(step(settle(preview))).ply, 4);
});

test('Black starts with one half-move, then advances pairs and reverses to the beginning', () => {
  const first = step(start(false));
  assert.equal(first.ply, 1);
  assert.equal(first.transition, null);
  const next = step(first);
  assert.deepEqual(next.transition, { via: 2, to: 3 });
  const back = step(settle(next), -1);
  assert.deepEqual(back.transition, { via: 2, to: 1 });
  assert.equal(settle(back).ply, 1);
  assert.equal(step(settle(back), -1).ply, 0);
});

test('stops use the actual FEN turn for games starting from a custom Black-to-move position', () => {
  assert.deepEqual(playerTurnStops(positions(6, false), true), [0, 1, 3, 5, 6]);
  assert.deepEqual(playerTurnStops(positions(6, false), false), [0, 2, 4, 6]);
});

test('the final board stays reachable for either player, regardless of the side to move', () => {
  for (const isWhite of [true, false]) {
    for (const last of [0, 1, 7, 8]) {
      let state = start(isWhite, last);
      for (let i = 0; i < last + 1; i++) state = settle(step(state));
      assert.equal(state.ply, last);
      assert.equal(state.transition, null);
      for (let i = 0; i < last + 1; i++) state = settle(step(state, -1));
      assert.equal(state.ply, 0);
    }
  }
});

test('rapid clicks advance from the pending destination and ignore the old timeout', () => {
  const first = step(start(true));
  const second = step(first);
  assert.deepEqual(second.transition, { via: 3, to: 4 });
  assert.equal(second.ply, 0);
  assert.equal(replayNavigation(second, { type: 'settle', transition: first.transition }), second);
  assert.equal(settle(second).ply, 4);
});

test('reversing or seeking during a preview cancels its destination', () => {
  const forward = step(start(true));
  const reverse = step(forward, -1);
  assert.deepEqual(reverse.transition, { via: 1, to: 0 });
  assert.equal(replayNavigation(reverse, { type: 'settle', transition: forward.transition }), reverse);
  assert.equal(settle(reverse).ply, 0);
  const sought = replayNavigation(forward, { type: 'seek', ply: 8 });
  assert.equal(sought.ply, 8);
  assert.equal(sought.transition, null);
  assert.equal(replayNavigation(sought, { type: 'settle', transition: forward.transition }), sought);
});

test('autoplay pauses safely within a pair and ignores queued automatic steps after pause', () => {
  let state = replayNavigation(start(false), { type: 'toggle-play' });
  state = step(state, 1, { automatic: true });
  assert.equal(state.ply, 1);
  assert.equal(state.playing, true);
  state = step(state, 1, { automatic: true });
  state = replayNavigation(state, { type: 'pause' });
  assert.equal(state.playing, false);
  assert.equal(step(state, 1, { automatic: true }), state);
  assert.equal(settle(state).ply, 3);
  assert.equal(settle(state).playing, false);
});

test('autoplay stops at the end and can restart, and manual navigation pauses it', () => {
  let state = replayNavigation(start(true, 3), { type: 'toggle-play' });
  state = settle(step(state, 1, { automatic: true }));
  state = settle(step(state, 1, { automatic: true }));
  assert.equal(state.ply, 3);
  assert.equal(state.playing, false);
  state = replayNavigation(state, { type: 'toggle-play' });
  assert.equal(state.ply, 0);
  assert.equal(state.playing, true);
  assert.equal(step(state).playing, false);
});

test('saved opponent turns restore to the preceding decision and invalid bookmarks stay in range', () => {
  const white = playerTurnStops(positions(8), true);
  const black = playerTurnStops(positions(8), false);
  assert.equal(restoreReplay(white, 3).ply, 2);
  assert.equal(restoreReplay(black, 2).ply, 1);
  assert.equal(restoreReplay(black, 0).ply, 0);
  assert.equal(restoreReplay(white, 3.5).ply, 2);
  for (const value of [NaN, Infinity, -5]) assert.equal(restoreReplay(white, value).ply, 0);
  assert.equal(restoreReplay(white, 1000).ply, 8);
});

test('reduced motion skips the brief board preview but preserves the same decision points', () => {
  const white = step(start(true), 1, { animate: false });
  assert.equal(white.ply, 2);
  assert.equal(white.transition, null);
  assert.equal(step(white, -1, { animate: false }).ply, 0);
  assert.equal(step(start(false), 1, { animate: false }).ply, 1);
});
