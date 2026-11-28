import test from 'node:test';
import assert from 'node:assert/strict';
import { combineAnalytics, emptySummary, groupedOutlook, ratePoints } from '../src/analyticsData.ts';

const row = (control, errors, moves) => ({...emptySummary(), time_class: 'blitz', time_control_raw: control,
  phase: {opening_errors: errors, opening_moves: moves}});

test('combining time controls weights error rates by moves, preserves zeros and missing samples', () => {
  const rows = [row('180+2', 1, 2), row('300', 1, 8)];
  const before = structuredClone(rows);
  const combined = combineAnalytics(rows);
  assert.deepEqual(ratePoints(combined.phase, ['Opening', 'Endgame']), [
    {label: 'Opening', errors: 2, moves: 10, rate: 20},
    {label: 'Endgame', errors: 0, moves: 0, rate: null},
  ]);
  assert.equal(ratePoints(combineAnalytics([row('600', 0, 4)]).phase, ['Opening'])[0].rate, 0);
  assert.deepEqual(rows, before);
});

test('all six piece rows and columns survive aggregation with actual piece on rows', () => {
  const a = row('180', 0, 0), b = row('300', 0, 0);
  a.piece_comparison.counts.pawn.knight = 2;
  b.piece_comparison.counts.pawn.knight = 3;
  b.piece_comparison.counts.knight.pawn = 1;
  const matrix = combineAnalytics([a, b]).piece_comparison.counts;
  assert.equal(Object.keys(matrix).length, 6);
  assert.ok(Object.values(matrix).every(inner => Object.keys(inner).length === 6));
  assert.equal(matrix.pawn.knight, 5);
  assert.equal(matrix.knight.pawn, 1);
});

test('positional chart folds Worse and Better while the original five-band data stays intact', () => {
  const counts = emptySummary().context_outlook.counts;
  counts.Losing.Attack = 2;
  counts.Worse.Attack = 3;
  counts.Equal.Improve = 4;
  counts.Better.Convert = 5;
  counts.Winning.Convert = 6;
  const before = structuredClone(counts);
  assert.deepEqual(groupedOutlook(counts), [
    {label: 'Losing', values: [5, 0, 0, 0]}, {label: 'Equal', values: [0, 0, 4, 0]},
    {label: 'Winning', values: [0, 0, 0, 11]},
  ]);
  assert.deepEqual(counts, before);
});
