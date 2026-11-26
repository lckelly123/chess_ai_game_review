import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdir, unlink} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {replayGame} from './fixtures/replayGame.mjs';
import {replayNavigation, replayStops, restoreReplay} from '../src/replayNavigation.ts';

const output = new URL(`../node_modules/.cache/replay-display-${process.pid}.mjs`, import.meta.url);
await mkdir(new URL('.', output), {recursive: true});
await build({entryPoints: [fileURLToPath(new URL('../src/Replay.tsx', import.meta.url))],
  bundle: true, platform: 'node', format: 'esm', packages: 'external', jsx: 'automatic', loader: {'.css': 'empty'}, outfile: fileURLToPath(output)});
const {default: Replay} = await import(output.href);
await unlink(output);

function render(ply, game = replayGame, username = game.black, completed = false) {
  const previousWindow = globalThis.window, previousStorage = globalThis.localStorage;
  globalThis.window = {matchMedia: () => ({matches: true})};
  globalThis.localStorage = {getItem: key => key === `position:${game.id}` ? String(ply)
    : completed && key.startsWith('review-practice:') ? JSON.stringify([{uci: 'b8b2', san: 'Qb2', at: 'now', quality: 'good', status: 'graded', lossPp: 0}]) : null};
  try { return renderToStaticMarkup(React.createElement(Replay, {game, username})); }
  finally {
    if (previousWindow === undefined) delete globalThis.window; else globalThis.window = previousWindow;
    if (previousStorage === undefined) delete globalThis.localStorage; else globalThis.localStorage = previousStorage;
  }
}

test('a new error shows its origin and destination in red, keeps the piece at its origin and reveals only the hint', () => {
  const html = render(1);
  assert.match(html, /Original move Qb4\+: from b8 to b4; both squares highlighted in red/);
  assert.match(html, /aria-label="b8, Black queen, original move origin"/);
  assert.match(html, /aria-label="b4, empty, original move destination"/);
  assert.equal((html.match(/class="square[^"]*error-move/g) ?? []).length, 2);
  assert.match(html, /original-move-arrow/);
  assert.match(html, /Find a better move than Qb4\+/);
  assert.match(html, /Consider the queen and king/);
  assert.doesNotMatch(html, /Review of Qb4|Saved assessment|Understand the position|candidate-arrow/);
  assert.match(html, /aria-label="Replay position" aria-valuetext="After Qb4\+, half-move 1"/);
});

test('a solved error restores the original move and its expanded assessment without repeating the exercise', () => {
  const html = render(1, replayGame, replayGame.black, true);
  assert.match(html, /Black queen b4/);
  assert.match(html, /Original move Qb4\+: from b8 to b4; both squares highlighted in red/);
  assert.match(html, /Played<\/span><div class="overview-played-move"><strong>12… Qb4\+<\/strong><span class="move-quality mistake">Mistake<\/span>/);
  assert.match(html, /<dt>Move evaluation<\/dt><dd class="unfavourable" title="Favours Black · depth 18">−5.00<\/dd>/);
  assert.match(html, /Review of Qb4\+/);
  assert.match(html, /Hide explanation for Qb4\+, player move/);
  assert.match(html, /Saved assessment of Qb4\+/);
  assert.doesNotMatch(html, /Black queen b8|Review of Qb2|Find a better move|candidate-arrow|original-move-arrow/);
  assert.match(html, /aria-label="Replay position" aria-valuetext="After Qb4\+, half-move 1"/);
});

test('each forward and backward step keeps the board, selected move and review on the same half-move', () => {
  let state = restoreReplay(replayStops(replayGame.positions), 0);
  assert.match(render(0), /Play a move to see its review/);
  assert.doesNotMatch(render(0), /class="square[^"]*last-move|Review of Qb4/);
  for (const direction of [1, 1, 1, -1, -1, -1]) {
    state = replayNavigation(state, {type: 'step', direction});
    const html = render(state.ply, replayGame, replayGame.black, true);
    if (state.ply) {
      const move = replayGame.moves[state.ply - 1];
      assert.ok(html.includes(`${move.color === 'black' ? 'Original move' : 'Last move'} ${move.san}: from ${move.uci.slice(0, 2)} to ${move.uci.slice(2, 4)}`));
      assert.ok(html.includes(`After ${move.san}, half-move ${state.ply}`));
    }
    assert.doesNotMatch(html, /Find a better move|candidate-arrow|original-move-arrow/);
  }
  assert.match(render(2), /Opponent’s moves/);
  assert.match(render(3, replayGame, replayGame.black, true), /Review of Qb2/);
  assert.match(render(3, replayGame, replayGame.black, true), /Black queen b2/);
  assert.match(render(3, replayGame, replayGame.black, true), /Final position/);
});

test('empty games and missing saved analysis keep an honest board without a next-move review', () => {
  const empty = {...replayGame, moves: [], positions: replayGame.positions.slice(0, 1), coach_responses: {}, engine_analyses: {}};
  assert.match(render(0, empty), /Starting position/);
  assert.doesNotMatch(render(0, empty), /Last move Qb4|Review of Qb4|candidate-arrow/);
  const missing = {...replayGame, coach_responses: {}, engine_analyses: {}};
  assert.match(render(1, missing), /Black queen b4/);
  assert.doesNotMatch(render(1, missing), /Review of Qb4|Find a better move|candidate-arrow/);
});
