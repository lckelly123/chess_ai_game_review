import test from 'node:test';
import assert from 'node:assert/strict';
import { clearAnalysisStorage } from '../src/analysisReset.ts';
import { practiceKey } from '../src/reviewPractice.ts';

function storage(keys) {
  const values = new Map(keys.map(key => [key, 'saved']));
  return {values, get length() { return values.size; }, key: i => [...values.keys()][i], removeItem: key => values.delete(key)};
}

test('one-game reset removes every attempt for both players and revisions, preserving other games and preferences', () => {
  const attempts = [practiceKey('one', 'white', 0, 'fen', 'e2e4'), practiceKey('one', 'black', 1, 'fen', 'e7e5', 2)];
  const keep = [practiceKey('two', 'white', 0, 'fen', 'e2e4'), 'position:two', 'coach-speech:v1:two:0:response:overview:123', 'username', 'coach-model', 'unrelated'];
  const saved = storage([...attempts, 'position:one', 'coach-speech:v1:one:0:response:overview:123', ...keep]);
  clearAnalysisStorage(saved, ['one']);
  assert.deepEqual([...saved.values.keys()], keep);
});

test('clear all removes practice for older game IDs and malformed practice keys, retaining account preferences', () => {
  const saved = storage([practiceKey('old-game', 'white', 0, 'fen', 'e2e4'), 'review-practice:v1:broken', 'position:old-game', 'coach-speech:v1:old-game:0:response:overview:123', 'username', 'coach-model']);
  clearAnalysisStorage(saved, [], true);
  assert.deepEqual([...saved.values.keys()], ['username', 'coach-model']);
});

test('server reset revisions prevent old attempts from returning on another browser', () => {
  const identity = ['game', 'white', 0, 'fen', 'e2e4'];
  assert.equal(practiceKey(...identity), practiceKey(...identity, 0));
  assert.notEqual(practiceKey(...identity), practiceKey(...identity, 1));
  assert.notEqual(practiceKey(...identity, 1), practiceKey(...identity, 2));
});
