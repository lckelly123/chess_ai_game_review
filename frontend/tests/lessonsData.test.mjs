import test from 'node:test';
import assert from 'node:assert/strict';
import { lessonCoverage } from '../src/lessonsData.ts';

test('lesson coverage distinguishes the analyzed sample from the whole library', () => {
  assert.equal(lessonCoverage({analyzed_games: 2, imported_games: 58, analyzed_moves: 104}), '2 of 58 games analyzed · 104 moves checked');
});
