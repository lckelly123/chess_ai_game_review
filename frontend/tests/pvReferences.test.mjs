import test from 'node:test';
import assert from 'node:assert/strict';
import { pvReferences } from '../src/pvReferences.ts';

const position = (name, turn, number) => ({fen: `${name} ${turn} - - 0 ${number}`, last_move: null, check_square: null});
const main = {san: ['Ne4', 'Nxe4', 'Qxe4', 'Be6', 'Bc4'], positions: [
  position('root', 'w', 12), position('Ne4', 'b', 12), position('Nxe4', 'w', 13),
  position('Qxe4', 'b', 13), position('Be6', 'w', 14), position('Bc4', 'b', 14),
]};
const lines = {c3e4: main};
const sequence = (text, source = lines, preferred = 'c3e4') => pvReferences(text, source, preferred).find(part => part.sequence)?.sequence;

test('an entire relevant excerpt is one link, rooted after omitted preceding moves', () => {
  const parts = pvReferences('It allows [[...Nxe4 Qxe4 Be6]], exchanging the knight.', lines, 'c3e4');
  assert.equal(parts.filter(part => part.sequence).length, 1);
  assert.deepEqual(parts[1].sequence.positions, main.positions.slice(1, 5));
  assert.deepEqual(parts[1].sequence.san, ['Nxe4', 'Qxe4', 'Be6']);
  assert.equal(parts.map(part => part.text).join(''), 'It allows ...Nxe4 Qxe4 Be6, exchanging the knight.');
});

test('numbered and Unicode Black continuations resolve; wrong move numbers and turns do not', () => {
  assert.ok(sequence('[[12…Nxe4 13. Qxe4 Be6]]'));
  assert.ok(sequence('[[…Nxe4 Qxe4]]'));
  assert.equal(sequence('[[12. Nxe4 Qxe4]]'), undefined);
  assert.equal(sequence('[[15...Nxe4 Qxe4]]'), undefined);
});

test('missing evidence, invented moves, UCI, and skipped intermediate moves stay plain text', () => {
  for (const text of ['[[Nxe4 Be6]]', '[[e2e4]]', '[[Qh9]]', '[[]]', '[[Nxe4 ... Be6]]', '[[Nxe4 ... Qxe4]]']) {
    assert.equal(sequence(text), undefined);
  }
  assert.equal(sequence('[[Nxe4 Qxe4]]', {}), undefined);
  assert.equal(sequence('[[Nxe4 Qxe4]]', {c3e4: {...main, positions: []}}), undefined);
  assert.equal(pvReferences('[[<script>alert(1)</script>]]')[0].text, '<script>alert(1)</script>');
});

test('alternative branches use their own starting position and ambiguous excerpts are not linked', () => {
  const alternate = {san: ['Be2', 'Nxe4', 'Qxe4'], positions: [main.positions[0], position('Be2', 'b', 12), position('other capture', 'w', 13), position('other queen', 'b', 13)]};
  const source = {...lines, f1e2: alternate};
  assert.deepEqual(sequence('[[Be2 Nxe4 Qxe4]]', source).positions, alternate.positions);
  assert.deepEqual(sequence('[[Nxe4 Qxe4]]', source).positions, main.positions.slice(1, 4));
  assert.equal(sequence('[[Nxe4 Qxe4]]', source, ''), undefined);
  const repeated = {san: ['Ne4', 'Nxe4', 'Qxe4', 'Nxe4', 'Qxe4'], positions: [...main.positions]};
  assert.equal(sequence('[[Nxe4 Qxe4]]', {c3e4: repeated}), undefined);
});

test('castling, promotion, checks, mate, and single-ply demonstrations use saved SAN', () => {
  const source = {e1g1: {san: ['O-O', 'a1=N+', 'Kh2#'], positions: main.positions.slice(0, 4)}};
  assert.deepEqual(sequence('[[0-0 a1=N+ Kh2#]]', source, 'e1g1').san, source.e1g1.san);
  assert.deepEqual(sequence('[[a1=N+]]', source).positions, source.e1g1.positions.slice(1, 3));
});
