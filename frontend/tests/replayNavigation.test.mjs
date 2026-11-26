import test from 'node:test';
import assert from 'node:assert/strict';
import { replayStops, replayNavigation, restoreReplay } from '../src/replayNavigation.ts';

const positions = (plies, first = 'w') => Array.from({length: plies + 1}, (_, ply) => ({fen: `board ${ply % 2 ? first === 'w' ? 'b' : 'w' : first} - - 0 1`}));
const start = (plies = 8, first = 'w') => restoreReplay(replayStops(positions(plies, first)), 0);
const step = (state, direction = 1, automatic = false) => replayNavigation(state, {type: 'step', direction, automatic});

test('one click advances exactly one half-move for either starting side', () => {
  for (const first of ['w', 'b']) {
    let state = start(8, first);
    assert.deepEqual(state.stops, [0, 1, 2, 3, 4, 5, 6, 7, 8]);
    for (let ply = 1; ply <= 8; ply++) { state = step(state); assert.equal(state.ply, ply); }
    assert.equal(step(state).ply, 8);
    for (let ply = 7; ply >= 0; ply--) { state = step(state, -1); assert.equal(state.ply, ply); }
    assert.equal(step(state, -1).ply, 0);
  }
});

test('rapid clicks and reversals use the current position without deferred transitions', () => {
  let state = start();
  state = step(step(step(state)));
  assert.equal(state.ply, 3);
  state = step(state, -1);
  assert.equal(state.ply, 2);
  assert.equal('transition' in state, false);
});

test('bookmarks retain opponent turns and clamp invalid positions', () => {
  const stops = replayStops(positions(8));
  for (const ply of [0, 1, 3, 8]) assert.equal(restoreReplay(stops, ply).ply, ply);
  assert.equal(restoreReplay(stops, 3.5).ply, 3);
  for (const value of [NaN, Infinity, -5]) assert.equal(restoreReplay(stops, value).ply, 0);
  assert.equal(restoreReplay(stops, 1000).ply, 8);
});

test('autoplay visits every half-move, stops at the end, and ignores stale ticks after pause', () => {
  let state = replayNavigation(start(3), {type: 'toggle-play'});
  for (let ply = 1; ply <= 3; ply++) { state = step(state, 1, true); assert.equal(state.ply, ply); }
  assert.equal(state.playing, false);
  state = replayNavigation(state, {type: 'toggle-play'});
  assert.equal(state.ply, 0);
  assert.equal(state.playing, true);
  state = replayNavigation(state, {type: 'pause'});
  assert.equal(step(state, 1, true).ply, 0);
});

test('seek and manual navigation pause autoplay; empty games cannot play', () => {
  const playing = replayNavigation(start(), {type: 'toggle-play'});
  assert.equal(step(playing).playing, false);
  const sought = replayNavigation(playing, {type: 'seek', ply: 3});
  assert.equal(sought.ply, 3);
  assert.equal(sought.playing, false);
  assert.equal(replayNavigation(start(0), {type: 'toggle-play'}).playing, false);
});
