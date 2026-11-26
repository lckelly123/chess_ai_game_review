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
await build({stdin: {contents: "export {default as CoachCards} from './CoachCards'; export {default as PracticeCard} from './PracticeCard'; export {default as MoveList} from './MoveList';",
  resolveDir: fileURLToPath(new URL('../src/', import.meta.url)), loader: 'tsx'},
  bundle: true, platform: 'node', format: 'esm', packages: 'external', jsx: 'automatic', outfile: fileURLToPath(output)});
const {CoachCards, PracticeCard, MoveList} = await import(pathToFileURL(fileURLToPath(output)).href);
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
const render = props => renderToStaticMarkup(React.createElement(CoachCards, {response, pending: false, transitioning: false, onSelectCandidate() {}, onPlaySequence() {}, ...props}));

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

test('selecting a candidate reveals only its explanation without the full engine continuation', () => {
  const html = render({selectedUci: 'e2e4'});
  assert.match(html, /Unique candidate detail/);
  assert.doesNotMatch(html, /Engine continuation/);
  assert.doesNotMatch(html, /Unique original move assessment|Error classification:|Missed tactic/);
  assert.doesNotMatch(render({selectedUci: undefined}), /Unique candidate detail|Engine continuation/);
});

test('the embedded original move opens its assessment and model classification without a continuation list', () => {
  const html = render({selectedUci: 'd2d4'});
  assert.match(html, /Unique original move assessment/);
  assert.match(html, /Hide explanation for d4, player move/);
  assert.match(html, /Error classification:/);
  assert.match(html, /Missed tactic/);
  assert.match(html, /Fork/);
  assert.doesNotMatch(html, /Engine continuation|Show d5, step 2/);
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

test('the compare button is absent even when a backend-derived target is available', () => {
  const current = {...response, better_candidate_uci: 'e2e4', stockfish: {
    perspective: 'White', move_quality: {status: 'blunder'},
    played_move: {uci: 'd2d4', san: 'd4', depth: 12, score: {cp: -200, mate: null, bound: 'exact'}},
  }};
  assert.doesNotMatch(render({response: current, selectedUci: 'd2d4'}), /Compare with/);
  assert.doesNotMatch(render({response: {...current, better_candidate_uci: null}, selectedUci: 'd2d4'}), /Compare with/);
});

test('an outdated coach contract is identified even when its taxonomy is current', () => {
  assert.match(render({response: {...response, coach_current: false, classification_current: true}}), /uses an earlier coach/);
  assert.doesNotMatch(render({response: {...response, coach_current: true, classification_current: true}}), /uses an earlier coach/);
});

test('saved tactic findings stay hidden while move details and continuation playback work', () => {
  const tactic_classification = {version: 1, fen: response.fen, played_move: response.played_move,
    status: 'classified', lines: [{direction: 'missed', motifs: ['fork'], coverage: 'bounded'},
      {direction: 'allowed', motifs: ['hanging_piece'], coverage: 'bounded'}]};
  const stockfish = {tactic_classification, perspective: 'White',
    played_move: {uci: 'd2d4', san: 'd4', depth: 12, score: {cp: -200, mate: null, bound: 'exact'}}};
  const engineReview = {fen: response.fen, played_move: response.played_move, stockfish};
  for (const currentResponse of [response, {...response, stockfish}, undefined]) {
    for (const selectedUci of [undefined, 'e2e4']) {
      const html = render({response: currentResponse, engineReview, selectedUci});
      assert.doesNotMatch(html, /tactic-classification|Tactic classification:|Missed: fork|Allowed: hanging piece|Not yet analysed/);
      assert.equal(html.includes('Unique candidate detail'), !!currentResponse && !!selectedUci);
      assert.doesNotMatch(html, /Engine continuation/);
      assert.doesNotMatch(html, /Unique original move assessment/);
    }
  }
});

test('move explanations render each verified PV sequence as one button and unresolved text without brackets', () => {
  const positions = ['root', 'e4', 'e5'].map((name, index) => ({fen: `${name} ${index % 2 ? 'b' : 'w'} - - 0 1`}));
  const current = {...response, move_lines: {e2e4: {san: ['e4', 'e5'], positions}},
    teaching: {...response.teaching, candidate_moves: [{...response.teaching.candidate_moves[0],
      reason: 'After [[e4 e5]], develop. Unavailable: [[Nf3 Nc6]].'}]}};
  const html = render({response: current, selectedUci: 'e2e4', activeSequenceId: 'e2e4:0:2'});
  assert.equal((html.match(/class="inline-move inline-pv"/g) ?? []).length, 1);
  assert.match(html, /aria-label="Play variation e4 e5" aria-pressed="true"/);
  assert.match(html, />e4 e5<\/button>/);
  assert.match(html, /Unavailable: Nf3 Nc6/);
  assert.doesNotMatch(html, /\[\[|Engine continuation|Compare with/);
});

test('legacy thesis stays readable with collapsed move explanations', () => {
  const html = render({response: {...response, teaching: {...response.teaching, position_overview: null,
    position_explanation: undefined, positional_thesis: 'A saved thesis.'}}});
  assert.match(html, /A saved thesis/);
  assert.match(html, />Moves</);
  assert.doesNotMatch(html, /Unique candidate detail|Unique original move assessment/);
});

test('the practice card keeps the hint spoiler-free and acknowledges success without a manual review step', () => {
  for (const complete of [false, true]) {
    const html = renderToStaticMarkup(React.createElement(PracticeCard, {
      overview: response.teaching.position_overview, original: {san: 'd4'},
      practice: {complete, attempts: complete ? [{quality: 'good'}] : [], shownMove: complete ? {san: 'e4'} : undefined, showReview() {}},
    }));
    assert.match(html, /The center needs attention/);
    assert.doesNotMatch(html, /Control the center with|Unique candidate detail|Unique original move assessment/);
    assert.doesNotMatch(html, /View review|Control the center with|Try another move/);
    assert.equal(html.includes('Good move. Let’s look at why.'), complete);
    assert.equal(html.includes('class="practice-feedback"'), complete);
  }
});

test('move list pairs actual move numbers, handles Black starts, missing evals and mate', () => {
  const moves = [{number: 23, color: 'black', san: 'O-O', uci: 'e8g8'}, {number: 24, color: 'white', san: 'a8=Q+', uci: 'a7a8q'},
    {number: 24, color: 'black', san: 'Qh2#', uci: 'h4h2'}];
  const positions = moves.map((_, index) => ({fen: `fen-${index}`}));
  const reviews = {'0': {fen: 'fen-0', played_move: 'e8g8', stockfish: {perspective: 'Black', played_move: {score: {cp: 105, mate: null, bound: 'exact'}}}},
    '2': {fen: 'fen-2', played_move: 'h4h2', stockfish: {perspective: 'Black', played_move: {score: {cp: null, mate: 1, bound: 'exact'}}}}};
  const list = ply => renderToStaticMarkup(React.createElement(MoveList, {moves, positions, reviews, ply, onSelect() {}}));
  const html = list(1);
  assert.match(html, />White<.*>Black</);
  assert.match(html, />23\.</); assert.match(html, />24\.</);
  assert.match(html, /Review 23… O-O, evaluation \+1.05 from Black/);
  assert.match(html, /Review 24. a8=Q\+, evaluation not available/);
  assert.match(html, /\+M1/);
  assert.equal((html.match(/aria-current="step"/g) ?? []).length, 1);
  assert.equal((html.match(/<button/g) ?? []).length, 3);
  assert.match(html, /aria-current="step"[^>]*title="Position after 23… O-O/);
  assert.doesNotMatch(list(0), /aria-current="step"/);
  assert.match(list(3), /aria-current="step"[^>]*title="Position after 24… Qh2#/);
});

test('opponent engine-only panel renders top three and the fourth played move with scores', () => {
  const top_moves = ['e7e5', 'c7c5', 'e7e6'].map((uci, index) => ({uci, san: ['e5', 'c5', 'e6'][index], depth: 12, score: {cp: 30 - index * 10, mate: null, bound: 'exact'}}));
  const played_move = {uci: 'a7a5', san: 'a5', depth: 12, score: {cp: -90, mate: null, bound: 'exact'}};
  const html = render({response: undefined, engineMode: true, opponent: true, engineReview: {fen: 'opponent', played_move: 'a7a5', stockfish: {perspective: 'Black', top_moves, played_move}}});
  assert.equal((html.match(/class="candidate-row/g) ?? []).length, 4);
  for (const value of ['+0.30', '+0.20', '+0.10', '−0.90']) assert.ok(html.includes(value));
  assert.doesNotMatch(html, /Understand the position/);
  assert.match(html, /Opponent move/);
});

test('selected player and opponent engine moves display their move, badge and evaluation only once', () => {
  const played_move = {uci: 'a7a5', san: 'a5', depth: 12, score: {cp: -90, mate: null, bound: 'exact'}};
  for (const opponent of [false, true]) {
    const html = render({response: undefined, engineMode: true, opponent, selectedUci: 'a7a5',
      engineReview: {fen: 'position', played_move: 'a7a5', stockfish: {perspective: 'Black', top_moves: [played_move], played_move}}});
    assert.equal((html.match(/>a5</g) ?? []).length, 1);
    assert.equal((html.match(/>−0.90</g) ?? []).length, 1);
    assert.equal((html.match(/class="player-move-badge"/g) ?? []).length, 1);
    assert.doesNotMatch(html, /class="move-detail"/);
  }
});

test('legacy move lists retain the selected explanation without duplicating its row heading', () => {
  const html = render({selectedUci: 'd2d4', response: {...response,
    teaching: {...response.teaching, position_overview: null, position_explanation: undefined, positional_thesis: 'A saved thesis.'}}});
  assert.equal((html.match(/>d4</g) ?? []).length, 1);
  assert.equal((html.match(/class="player-move-badge"/g) ?? []).length, 1);
  assert.match(html, /Unique original move assessment/);
  assert.match(html, /Error classification:/);
});
