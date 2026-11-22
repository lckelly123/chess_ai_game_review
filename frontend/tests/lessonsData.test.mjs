import test from 'node:test';
import assert from 'node:assert/strict';
import { combineErrorCounts, filteredLessonRows, lessonCoverage, lessonGroupCounts, severitySummary } from '../src/lessonsData.ts';

test('lesson coverage distinguishes the analyzed sample from the whole library', () => {
  assert.equal(lessonCoverage({analyzed_games: 2, imported_games: 58, analyzed_moves: 104}), '2 of 58 games analyzed · 104 moves checked');
});

const counts = (inaccuracy = 0, mistake = 0, blunder = 0) => ({inaccuracy, mistake, blunder, total: inaccuracy + mistake + blunder});
const row = (key, label, values) => ({key, label, counts: values});

test('overview combines both tactical categories and preserves all unclassified counts', () => {
  const data = {categories: [
    {key: 'positional', counts: counts(7, 2, 1)},
    {key: 'tactical_miss', counts: counts(0, 1, 2)},
    {key: 'tactical_allowed', counts: counts(0, 1, 1)},
  ], unclassified: counts(1, 1, 1)};
  const before = structuredClone(data);
  const groups = lessonGroupCounts(data);
  assert.deepEqual(groups.positional, counts(7, 2, 1));
  assert.deepEqual(groups.tactical, counts(0, 2, 3));
  assert.deepEqual(groups.unclassified, counts(1, 1, 1));
  assert.deepEqual(combineErrorCounts(Object.values(groups)), counts(8, 5, 5));
  assert.deepEqual(data, before);
});

test('severity filters rank matching topics and omit zeros without changing saved data', () => {
  const category = {subcategories: [row('fork', 'Fork', counts(4, 0, 1)), row('hanging_piece', 'Hanging piece', counts(1, 0, 2)),
    row('pin_skewer', 'Pin / skewer', counts()), row('discovered_attack', 'Discovered attack', counts(0, 1, 2))]};
  const before = structuredClone(category);
  const all = filteredLessonRows(category, 'all');
  assert.deepEqual(all.map(item => [item.key, item.matching]), [['fork', 5], ['discovered_attack', 3], ['hanging_piece', 3]]);
  const blunders = filteredLessonRows(category, 'blunder');
  assert.deepEqual(blunders.map(item => [item.key, item.matching]), [['discovered_attack', 2], ['hanging_piece', 2], ['fork', 1]]);
  assert.equal(blunders.reduce((total, item) => total + item.matching, 0), 5);
  assert.deepEqual(category, before);
});

test('missing categories and unmatched severity produce empty results', () => {
  assert.deepEqual(lessonGroupCounts({categories: [], unclassified: counts(1)}), {
    positional: counts(), tactical: counts(), unclassified: counts(1),
  });
  assert.deepEqual(filteredLessonRows(undefined, 'all'), []);
  assert.deepEqual(filteredLessonRows({subcategories: [row('pawn', 'Pawn', counts(3))]}, 'blunder'), []);
  assert.deepEqual(combineErrorCounts([]), counts());
});

test('summary labels omit zero severities and handle singular and empty counts', () => {
  assert.equal(severitySummary(counts(7, 2, 1)), '7 inaccuracies · 2 mistakes · 1 blunder');
  assert.equal(severitySummary(counts(1, 0, 2)), '1 inaccuracy · 2 blunders');
  assert.equal(severitySummary(counts()), 'No errors');
});
