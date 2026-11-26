import test from 'node:test';
import assert from 'node:assert/strict';
import { engineMoves, engineSelectionId, visibleEngineCandidate, errorMarkers, analysisProgress, coachingPending, coachedErrorPlies, mergeCoachResponses } from '../src/engineReview.ts';
import { replayStops, replayNavigation, restoreReplay } from '../src/replayNavigation.ts';

const engineMove = (uci, san, cp, rank) => ({uci, san, rank, depth: 12, score: {cp, mate: null, bound: 'exact'}});
const top = [engineMove('e2e4', 'e4', 50, 1), engineMove('d2d4', 'd4', 40, 2), engineMove('g1f3', 'Nf3', 35, 3), engineMove('c2c4', 'c4', 20, 4)];
const review = {fen: 'position', played_move: 'g2g4', stockfish: {perspective: 'White', top_moves: top, played_move: engineMove('g2g4', 'g4', -200, null), move_quality: {status: 'blunder'}}};

test('engine-only rows show top three in ranking order plus the player, without commentary', () => {
  const before = structuredClone(review);
  const rows = engineMoves(review);
  assert.deepEqual(rows.map(move => move.uci), ['e2e4', 'd2d4', 'g1f3', 'g2g4']);
  assert.deepEqual(rows.map(move => move.engineMove.score.cp), [50, 40, 35, -200]);
  assert.equal(rows.filter(move => move.isPlayed).length, 1);
  assert(rows.every(move => move.reason === '' && !move.feedback));
  assert.deepEqual(rows[3].highlight_squares, ['g2', 'g4']);
  assert.deepEqual(review, before);
});

test('a top-three played move is marked once; fourth-ranked played move is appended', () => {
  for (let index = 0; index < top.length; index++) {
    const selected = {...review, played_move: top[index].uci, stockfish: {...review.stockfish, played_move: top[index]}};
    const rows = engineMoves(selected);
    assert.equal(rows.length, index < 3 ? 3 : 4);
    assert.equal(rows.filter(move => move.isPlayed).length, 1);
    assert.equal(rows.find(move => move.isPlayed).uci, top[index].uci);
  }
});

test('fewer legal candidates, castling and promotion keep correct overlays', () => {
  for (const uci of ['e1g1', 'e7e8q']) {
    const only = engineMove(uci, 'move', 100, 1);
    const result = {...review, played_move: uci, stockfish: {...review.stockfish, top_moves: [only], played_move: only}};
    assert.equal(engineMoves(result).length, 1);
    assert.deepEqual(engineMoves(result)[0].highlight_squares, [uci.slice(0, 2), uci.slice(2, 4)]);
  }
  assert.deepEqual(engineMoves(), []);
});

test('engine board previews reject stale positions, transitions and undisplayed moves', () => {
  const selection = {fen: review.fen, responseId: engineSelectionId(review), uci: 'e2e4'};
  assert.equal(visibleEngineCandidate(selection, review, review.fen, false).uci, 'e2e4');
  assert.equal(visibleEngineCandidate({...selection, uci: 'g2g4'}, review, review.fen, false).isPlayed, true);
  assert.equal(visibleEngineCandidate({...selection, uci: 'c2c4'}, review, review.fen, false), undefined);
  assert.equal(visibleEngineCandidate(selection, review, 'other', false), undefined);
  assert.equal(visibleEngineCandidate(selection, review, review.fen, true), undefined);
  assert.equal(visibleEngineCandidate({...selection, responseId: 'old-coach'}, review, review.fen, false), undefined);
});

test('timeline markers target pre-move player stops, skip Good/Uncertain and reject stale evidence', () => {
  const positions = Array.from({length: 11}, (_, ply) => ({fen: `${ply} ${ply % 2 ? 'b' : 'w'} - - 0 1`}));
  const moves = positions.slice(0, -1).map((_, ply) => ({uci: `uci-${ply}`, color: ply % 2 ? 'black' : 'white', san: `san-${ply}`, number: Math.floor(ply / 2) + 1}));
  const reviews = Object.fromEntries(moves.map((move, ply) => [ply, {fen: positions[ply].fen, played_move: move.uci,
    stockfish: {move_quality: {status: ['good', 'inaccuracy', 'mistake', 'blunder', 'uncertain'][Math.floor(ply / 2)]}}}]));
  for (const [isWhite, color, expected] of [[true, 'white', [2, 4, 6]], [false, 'black', [3, 5, 7]]]) {
    const stops = replayStops(positions, isWhite);
    const markers = errorMarkers(moves, positions, stops, reviews, color);
    assert.deepEqual(markers.map(marker => marker.ply), expected);
    for (const marker of markers) {
      assert.equal(marker.percent, stops.indexOf(marker.ply) * 100 / (stops.length - 1));
      assert.equal(replayNavigation(restoreReplay(stops, 0), {type: 'seek', ply: marker.ply}).ply, marker.ply);
      assert(marker.label.includes(moves[marker.ply].san));
    }
  }
  reviews['2'].fen = 'outdated'; reviews['4'].played_move = 'different';
  assert.deepEqual(errorMarkers(moves, positions, replayStops(positions, true), reviews, 'white').map(marker => marker.ply), [6]);
});

test('custom Black-to-move start and short games use the actual stop index', () => {
  const positions = [{fen: 'start b - - 0 30'}, {fen: 'after w - - 1 31'}];
  const moves = [{uci: 'e8g8', san: 'O-O', number: 30, color: 'black'}];
  const reviews = {'0': {fen: positions[0].fen, played_move: 'e8g8', stockfish: {move_quality: {status: 'mistake'}}}};
  const markers = errorMarkers(moves, positions, replayStops(positions, false), reviews, 'black');
  assert.equal(markers[0].percent, 0);
  assert.equal(markers[0].label, '30… O-O — Mistake');
  assert.equal(analysisProgress({status: 'running', completed: 18, total: 42}), 'Analyzing 18/42 moves');
});

test('game progress distinguishes pending, active, paused and saved coaching', () => {
  const analysis = {completed: 60, total: 60, coach_total: 5, coach_completed: 2};
  assert.equal(analysisProgress({...analysis, status: 'running'}), 'Coaching 2/5 flagged moves');
  assert.equal(analysisProgress({...analysis, status: 'failed'}), 'Coaching paused · 2/5 flagged moves');
  assert.equal(analysisProgress({...analysis, status: 'completed'}), '60 moves analyzed · Coach reviews pending');
  assert.equal(coachingPending(analysis), true);
  assert.equal(coachingPending({...analysis, coach_completed: 5}), false);
  assert.equal(analysisProgress({...analysis, coach_completed: 5, status: 'completed'}), '60 moves analyzed · 5 coach reviews saved');
  assert.equal(analysisProgress({...analysis, coach_total: 0, coach_completed: 0, status: 'completed'}), '60 moves analyzed');
});

test('live automatic reviews merge without replacing a newer manual response', () => {
  const old = {response_id: 'old', created_at: '2026-11-18T12:00:00Z'};
  const current = {response_id: 'manual', created_at: '2026-11-18T13:00:00Z'};
  const automatic = {response_id: 'automatic', created_at: '2026-11-18T13:01:00Z'};
  const before = {'2': current};
  assert.deepEqual(mergeCoachResponses(before, {'2': old, '4': automatic}), {'2': current, '4': automatic});
  assert.deepEqual(mergeCoachResponses(before, {'2': automatic}), {'2': automatic});
  assert.deepEqual(before, {'2': current});
});

test('review arrows select only matching player errors with a saved full response', () => {
  const positions = Array.from({length: 13}, (_, ply) => ({fen: `position-${ply}`}));
  const moves = positions.slice(0, -1).map((_, ply) => ({uci: `move-${ply}`, color: ply % 2 ? 'black' : 'white'}));
  const reviews = Object.fromEntries(moves.map((move, ply) => [ply, {fen: positions[ply].fen, played_move: move.uci,
    stockfish: {move_quality: {status: ['good', 'inaccuracy', 'mistake', 'blunder', 'uncertain', 'blunder'][Math.floor(ply / 2)]}}}]));
  const responses = Object.fromEntries(moves.map((move, ply) => [ply, {...reviews[ply], teaching: {position_explanation: 'Full review.'}}]));
  delete responses[10]; // Engine result exists, but coaching has not finished.
  assert.deepEqual(coachedErrorPlies(moves, positions, reviews, responses, 'white'), [2, 4, 6]);
  assert.deepEqual(coachedErrorPlies(moves, positions, reviews, responses, 'black'), [3, 5, 7, 11]);
  responses[2].fen = 'stale'; responses[4].played_move = 'other'; responses[6].teaching.position_explanation = '';
  assert.deepEqual(coachedErrorPlies(moves, positions, reviews, responses, 'white'), []);
});

test('engine progress includes opponent searches before entering the coaching phase', () => {
  const analysis = {status: 'running', total: 20, completed: 20, opponent_total: 19, opponent_completed: 5, coach_total: 3, coach_completed: 0};
  assert.equal(analysisProgress(analysis), 'Analyzing 25/39 moves');
  assert.equal(analysisProgress({...analysis, opponent_completed: 19}), 'Coaching 0/3 flagged moves');
  assert.equal(analysisProgress({...analysis, status: 'completed', opponent_total: null, opponent_completed: 0}), '20 moves analyzed · Opponent analysis pending');
});
