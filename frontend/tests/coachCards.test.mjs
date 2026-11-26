import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, unlink } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

// Compile the real TSX components with the app's existing build tool.
const directory = new URL('../node_modules/.cache/', import.meta.url);
await mkdir(directory, {recursive: true});
const output = new URL(`coach-cards-${process.pid}.mjs`, directory);
await build({stdin: {contents: "export {default as CoachCards} from './CoachCards'; export {default as PracticeCard} from './PracticeCard';",
  resolveDir: fileURLToPath(new URL('../src/', import.meta.url)), loader: 'tsx'},
  bundle: true, platform: 'node', format: 'esm', packages: 'external', jsx: 'automatic', outfile: fileURLToPath(output)});
const {CoachCards, PracticeCard} = await import(pathToFileURL(fileURLToPath(output)).href);
await unlink(output);

const response = {
  fen: '8/8/8/8/8/8/8/8 w - - 0 1', played_move: 'd2d4', text: '',
  teaching: {position_overview: 'The center needs attention.',
    position_explanation: 'Control the center with [[e2e4]].\n\nYour move, [[d2d4]], misses the stronger continuation.',
    candidate_moves: [{uci: 'e2e4', reason: 'Unique candidate detail.', highlight_squares: ['e4', 'd5']}],
    move_evaluation: {explanation: 'Unique original move assessment.', mistake_classification: {category: 'tactical_miss', subcategory: 'fork'}}},
  candidate_san: {e2e4: 'e4', d2d4: 'd4'},
  move_lines: {e2e4: {san: ['e4', 'e5'], positions: []}, d2d4: {san: ['d4', 'd5'], positions: []}},
};
const render = props => renderToStaticMarkup(React.createElement(CoachCards, {response, pending: false, transitioning: false, onSelectCandidate() {}, onSelectLinePly() {}, ...props}));

test('the revealed review contains inline SAN buttons but no move-specific details until selected', () => {
  const html = render();
  assert.match(html, /class="inline-move"/);
  assert.match(html, /Show explanation for e4/);
  assert.match(html, /Show explanation for d4, player move/);
  assert.equal((html.match(/class="teaching-paragraph"/g) ?? []).length, 2);
  assert.match(html, /<\/p><p class="teaching-paragraph">Your move,/);
  assert.doesNotMatch(html, /\[\[e2e4\]\]|Unique candidate detail|Unique original move assessment|Engine continuation|Missed tactic|Fork/);
  assert.doesNotMatch(html, />Moves<|>Your move<|candidate-row|Positional thesis|Error classification:/);
});

test('selecting a candidate reveals only its detail and continuation; clearing it hides both', () => {
  const html = render({selectedUci: 'e2e4'});
  assert.match(html, /Unique candidate detail/);
  assert.match(html, /Engine continuation/);
  assert.doesNotMatch(html, /Unique original move assessment|Error classification:|Missed tactic/);
  assert.doesNotMatch(render({selectedUci: undefined}), /Unique candidate detail|Engine continuation/);
});

test('the embedded original move opens its assessment, model classification, and continuation', () => {
  const html = render({selectedUci: 'd2d4'});
  assert.match(html, /Unique original move assessment/);
  assert.match(html, /Hide explanation for d4, player move/);
  assert.match(html, /Error classification:/);
  assert.match(html, /Missed tactic/);
  assert.match(html, /Fork/);
  assert.match(html, /Engine continuation/);
  assert.match(html, /Show d5, step 2/);
  assert.doesNotMatch(html, /Unique candidate detail|Show e5, step 2/);
  assert.doesNotMatch(render({selectedUci: undefined}), /Unique original move assessment|Error classification:|Engine continuation/);
});

test('model error labels cover allowed tactics and normalized positional errors', () => {
  for (const [mistake_classification, labels] of [
    [{category: 'tactical_allowed', subcategory: 'pin_skewer'}, ['Allowed tactic', 'Pin / skewer']],
    [{category: 'positional', subcategory: 'bishop'}, ['Positional', 'Bishop']],
  ]) {
    const current = {...response, teaching: {...response.teaching,
      move_evaluation: {...response.teaching.move_evaluation, mistake_classification}}};
    const html = render({response: current, selectedUci: 'd2d4'});
    for (const label of labels) assert.ok(html.includes(label));
  }
});

test('a good played candidate reuses its explanation without an error classification or extra move row', () => {
  const current = {...response, played_move: 'e2e4', teaching: {...response.teaching,
    position_explanation: 'Control the center with [[e2e4]].\n\nYour move, [[e2e4]], follows this plan.',
    move_evaluation: {explanation: null, mistake_classification: null}}};
  const html = render({response: current, selectedUci: 'e2e4'});
  assert.equal((html.match(/Unique candidate detail/g) ?? []).length, 1);
  assert.equal((html.match(/class="teaching-paragraph"/g) ?? []).length, 2);
  assert.match(html, /Hide explanation for e4, player move/);
  assert.doesNotMatch(html, /Error classification:|candidate-row|Your move was/);
});

test('saved inline reviews without a player link retain access through a neutral embedded reference', () => {
  const current = {...response, teaching: {...response.teaching, position_explanation: 'Control the center with [[e2e4]].'}};
  const html = render({response: current});
  assert.match(html, /Your move was/);
  assert.match(html, /Show explanation for d4, player move/);
  assert.doesNotMatch(html, /candidate-row|Unique original move assessment/);
  assert.doesNotMatch(render({response: {...current, played_move: null}}), /Your move was|player move|Error classification:/);
});

test('comparison uses the backend-derived target without a model comparison field', () => {
  const current = {...response, better_candidate_uci: 'e2e4', stockfish: {
    perspective: 'White', move_quality: {status: 'blunder'},
    played_move: {uci: 'd2d4', san: 'd4', depth: 12, score: {cp: -200, mate: null, bound: 'exact'}},
  }};
  assert.match(render({response: current, selectedUci: 'd2d4'}), /Compare with e4/);
  assert.doesNotMatch(render({response: {...current, better_candidate_uci: null}, selectedUci: 'd2d4'}), /Compare with/);
});

test('an outdated coach contract is identified even when its taxonomy is current', () => {
  assert.match(render({response: {...response, coach_current: false, classification_current: true}}), /uses an earlier coach/);
  assert.doesNotMatch(render({response: {...response, coach_current: true, classification_current: true}}), /uses an earlier coach/);
});

test('saved tactic findings coexist with staged move details and continuation playback', () => {
  const tactic_classification = {version: 1, fen: response.fen, played_move: response.played_move,
    status: 'classified', lines: [{direction: 'missed', motifs: ['fork'], coverage: 'bounded'},
      {direction: 'allowed', motifs: ['hanging_piece'], coverage: 'bounded'}]};
  const engineReview = {fen: response.fen, played_move: response.played_move, stockfish: {tactic_classification}};
  for (const selectedUci of [undefined, 'e2e4']) {
    const html = render({engineReview, selectedUci});
    assert.match(html, /Tactic classification:/);
    assert.match(html, /Missed: fork · Allowed: hanging piece/);
    assert.equal(html.includes('Unique candidate detail'), !!selectedUci);
    assert.equal(html.includes('Engine continuation'), !!selectedUci);
    assert.doesNotMatch(html, /Unique original move assessment/);
  }
});

test('legacy thesis stays readable with collapsed move explanations', () => {
  const html = render({response: {...response, teaching: {...response.teaching, position_overview: null,
    position_explanation: undefined, positional_thesis: 'A saved thesis.'}}});
  assert.match(html, /A saved thesis/);
  assert.match(html, />Moves</);
  assert.doesNotMatch(html, /Unique candidate detail|Unique original move assessment/);
});

test('the practice card shows only the overview both during and after the exercise', () => {
  for (const complete of [false, true]) {
    const html = renderToStaticMarkup(React.createElement(PracticeCard, {
      overview: response.teaching.position_overview, original: {san: 'd4'},
      practice: {complete, attempts: [], shownMove: complete ? {san: 'e4'} : undefined, showReview() {}},
    }));
    assert.match(html, /The center needs attention/);
    assert.doesNotMatch(html, /Control the center with|Unique candidate detail|Unique original move assessment/);
    assert.equal(html.includes('View review'), complete);
  }
});
