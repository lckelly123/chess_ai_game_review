import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdir, unlink} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {evaluationPercent, moveTime, overviewCounts, overviewTimeline} from '../src/overviewData.ts';

const output = new URL(`../node_modules/.cache/game-overview-${process.pid}.mjs`, import.meta.url);
await mkdir(new URL('.', output), {recursive: true});
await build({stdin: {contents: "export {default as GameOverview} from './GameOverview'; export {default as Board} from './Board';", resolveDir: fileURLToPath(new URL('../src/', import.meta.url)), loader: 'tsx'},
  bundle: true, platform: 'node', format: 'esm', packages: 'external', jsx: 'automatic', loader: {'.css': 'empty'}, outfile: fileURLToPath(output)});
const {GameOverview, Board} = await import(output.href);
await unlink(output);

const game = {white: 'White player', black: 'Black player', positions: [
  {fen: '8/8/8/8/8/8/4P3/4K2k w - - 0 1', phase: 'endgame'},
  {fen: '8/8/8/8/4P3/8/8/4K2k b - - 0 1', phase: 'endgame'},
  {fen: '8/8/8/8/4P3/8/7k/4K3 w - - 1 2', phase: 'endgame'},
], moves: [{number: 1, color: 'white', san: 'e4', uci: 'e2e4', ply: 1, elapsed_seconds: 12.5}, {number: 1, color: 'black', san: 'Kh2', uci: 'h1h2', ply: 2}]};
const candidate = (cp, uci = 'e2e4') => ({uci, san: uci === 'e2e4' ? 'e4' : 'Kh2', depth: 18, score: {cp, mate: null, bound: 'exact'}});
const reviews = {
  0: {fen: game.positions[0].fen, played_move: 'e2e4', stockfish: {perspective: 'White', top_moves: [candidate(50)], played_move: candidate(-200), move_quality: {status: 'mistake'}},
    position_evidence: {decision_classification: 'selective', unclassified_reason: null, sharpness: {version: 2, score: 43.1}}},
  1: {fen: game.positions[1].fen, played_move: 'h1h2', stockfish: {perspective: 'Black', top_moves: [candidate(-80, 'h1h2')], played_move: candidate(-80, 'h1h2'), move_quality: {status: 'good'}}},
};
const render = extra => renderToStaticMarkup(React.createElement(GameOverview, {game, reviews, ply: 0, onSelect() {}, onMainLine: true, analyzing: false, submitting: false, onComplete() {}, ...extra}));

test('timeline uses unrestricted root scores, normalizes Black, and keeps gaps', () => {
  const timeline = overviewTimeline(game, reviews);
  assert.deepEqual(timeline.map(point => point.cp ?? null), [50, 80, null]);
  assert.equal(timeline[2].status, 'missing');
  assert.equal(overviewTimeline(game, {...reviews, 1: {...reviews[1], fen: 'stale'}})[1].status, 'missing');
  assert.equal(evaluationPercent({status: 'terminal', mate: 0, mate_winner: 'white'}) > 95, true);
  assert.equal(evaluationPercent({status: 'terminal', mate: 0, mate_winner: 'black'}) < 5, true);
  assert.equal(evaluationPercent({status: 'missing'}), null);
});

test('counts include both players and do not classify missing or uncertain moves as Good', () => {
  const counts = overviewCounts(game, reviews);
  assert.equal(counts.white.mistake, 1);
  assert.equal(counts.black.good, 1);
  assert.equal(counts.white.good, 0);
  assert.equal(overviewCounts(game, {}) .white.analysed, 0);
});

test('position and next-move facts stay separate and fixed player columns do not depend on board orientation', () => {
  const html = render();
  assert.match(html, /White player.*Black player/);
  assert.match(html, /Selective/);
  assert.match(html, /43<small> \/ 100/);
  assert.match(html, /<h2>Position sharpness<\/h2>/);
  assert.match(html, /Played<\/span><div class="overview-played-move"><strong>1\. e4<\/strong><span class="move-quality mistake">Mistake<\/span><\/div>/);
  assert.match(html, /12.5s/);
  assert.match(html, /−2.00/); // Played score; graph instead uses +0.50.
  assert.match(html, /Endgame/);
  assert.doesNotMatch(html, /move-list-scroll/);
  assert.match(html, /<dt>Move evaluation<\/dt>/);
  assert.doesNotMatch(html, /<small>[^<]*perspective/);
});

test('Black played-move evaluation uses White perspective while preserving its move grade', () => {
  const html = render({ply: 1});
  assert.match(html, /<strong>1… Kh2<\/strong><span class="move-quality good">Good<\/span>/);
  assert.match(html, /<dt>Move evaluation<\/dt><dd class="favourable" title="Favours White · depth 18">\+0\.80<\/dd>/);
});

test('missing or stale reviews cannot supply a played classification or evaluation', () => {
  for (const evidence of [{}, {0: {...reviews[0], fen: 'stale'}}]) {
    const html = render({reviews: evidence});
    assert.match(html, /<strong>1\. e4<\/strong>/);
    assert.doesNotMatch(html, /class="move-quality/);
    assert.match(html, /<dt>Move evaluation<\/dt><dd class="">—<\/dd>/);
  }
});

test('variation and final position cannot retain the next move time or evaluation', () => {
  for (const html of [render({onMainLine: false}), render({ply: 2})]) {
    assert.doesNotMatch(html, /12.5s|−2.00|>1\. e4<|>Selective</);
    assert.doesNotMatch(html, /class="move-quality/);
  }
  assert.match(render({onMainLine: false}), /Exploring variation/);
  assert.match(render({ply: 2}), /End of game/);
});

test('accuracy only appears for a complete, matching versioned timeline', () => {
  const statistics = {version: 1, perspective: 'White', complete: true, accuracy: {white: 88.14, black: 76.36},
    timeline: overviewTimeline(game, reviews).map(point => ({...point, status: 'evaluated', cp: point.cp ?? 0}))};
  assert.match(render({statistics}), /88.1%/);
  assert.match(render({statistics}), /76.4%/);
  assert.doesNotMatch(render({statistics: {...statistics, complete: false}}), /88.1%|76.4%/);
  const stale = {...statistics, timeline: statistics.timeline.map((point, ply) => ply === 0 ? {...point, fen: 'stale'} : point)};
  assert.doesNotMatch(render({statistics: stale}), /88.1%|76.4%/);
});

test('purple recorded-move arrow follows board flip and does not recolour any squares', () => {
  const board = extra => renderToStaticMarkup(React.createElement(Board, {position: game.positions[0], flipped: false, originalMove: game.moves[0], ...extra}));
  assert.match(board(), /purple arrow from e2 to e4/);
  assert.match(board(), /x1="4.5" y1="6.5" x2="4.5" y2="4.5"/);
  assert.match(board({flipped: true}), /x1="3.5" y1="1.5" x2="3.5" y2="3.5"/);
  assert.doesNotMatch(board(), /class="square[^\"]*original-move/);
  assert.doesNotMatch(board({originalMove: undefined}), /original-move-arrow|Recorded move played next/);
});

test('timing preserves zero and fractional seconds and displays unknown honestly', () => {
  assert.equal(moveTime(0), '0s');
  assert.equal(moveTime(12.5), '12.5s');
  assert.equal(moveTime(75), '1m 15s');
  assert.equal(moveTime(null), '—');
});
