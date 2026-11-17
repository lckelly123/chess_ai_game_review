import test from 'node:test';
import assert from 'node:assert/strict';
import { parseCoachContent, engineEvaluation } from '../src/coachContent.ts';

const saved = `### 1. Understand the Position

**Key Positional Factors**

- **Pawn Structure:** The center restricts the knight.
- **Piece Activity:** Develop with **...Nge7**.
  Keep the pieces coordinated.
- **King Safety:** Both kings are in the center.

**Positional Thesis**

Challenge the center without rushing.

### 2. Develop a Plan

**Strategic Objective**

Improve the knight.

**How to Approach the Position**

Connect development to central pressure.

**Moves to Look For**

- **6...Qb6** is a candidate, not part of the approach.

### 3. Evaluate Your Move

**Your Move: 6...Nge7**

This follows the plan. After **7.Nc3 Nf5**, it pressures d4.

**Better Alternatives**

Keep this second-pass subsection if the coach included it.`;

test('splits saved reviews without losing factor or move-review content', () => {
  const content = parseCoachContent(saved);
  assert.deepEqual(content.factors.map(f => f.title), ['Pawn Structure', 'Piece Activity', 'King Safety']);
  assert.equal(content.factors[0].body, 'The center restricts the knight.');
  assert.match(content.factors[1].body, /\*\*\.\.\.Nge7\*\*/);
  assert.match(content.factors[1].body, /Keep the pieces coordinated/);
  assert.equal(content.thesis, 'Challenge the center without rushing.');
  assert.equal(content.objective, 'Improve the knight.');
  assert.equal(content.approach, 'Connect development to central pressure.');
  assert.doesNotMatch(JSON.stringify(content), /6\.\.\.Qb6/);
  assert.match(content.evaluation, /6\.\.\.Nge7/);
  assert.match(content.evaluation, /Better Alternatives/);
});

test('supports numbered ranked factors, heading labels, and inline bold labels', () => {
  const content = parseCoachContent(`## 1. Understand the Position
### Key Positional Factors
1. **King Safety:** Stop the threat.
2. **Pawn Structure:** Defend the center.
3. **Piece Activity:** Connect the rooks.
#### Positional Thesis
Keep the king safe.
## 2. Develop a Plan
**Strategic Objective:** Defend first.
### B. Explain the Chess Reasoning
Safety takes priority.
### C. Find Candidate Moves
Do not display this old subsection.`);
  assert.equal(content.factors.length, 3);
  assert.equal(content.factors[0].title, 'King Safety');
  assert.equal(content.thesis, 'Keep the king safe.');
  assert.equal(content.objective, 'Defend first.');
  assert.equal(content.approach, 'Safety takes priority.');
  assert.equal(content.evaluation, '');
  assert.doesNotMatch(JSON.stringify(content), /Do not display/);
});

test('preserves legacy freeform text and does not mistake inline phrases for headings', () => {
  const content = parseCoachContent('A saved position explanation mentions **Positional Thesis** mid-sentence.');
  assert.match(content.positionIntro, /saved position explanation/);
  assert.match(content.positionIntro, /mid-sentence/);
  assert.equal(content.factors.length, 0);
  assert.equal(parseCoachContent('').evaluation, '');
});

const engine = (cp, perspective = 'Black', mate = null, bound = 'exact') => ({
  engine: 'Stockfish', perspective,
  played_move: { san: 'Nge7', uci: 'g8e7', rank: 1, depth: 18, score: { cp, mate, bound } },
});

test('negative Black-perspective score favours White even for the first-ranked move', () => {
  assert.deepEqual(engineEvaluation(engine(-46)), { value: '−0.46', tone: 'unfavourable', label: 'Favours White', perspective: 'Black' });
  assert.equal(engineEvaluation(engine(46)).label, 'Favours Black');
  assert.equal(engineEvaluation(engine(-46, 'White')).label, 'Favours Black');
});

test('handles balanced scores, forced mates, checkmate, and engine bounds honestly', () => {
  assert.equal(engineEvaluation(engine(0)).value, '0.00');
  assert.equal(engineEvaluation(engine(20)).tone, 'neutral');
  assert.equal(engineEvaluation(engine(null, 'White', 3)).label, 'White has mate in 3');
  assert.equal(engineEvaluation(engine(null, 'Black', -2)).value, '−M2');
  assert.equal(engineEvaluation(engine(null, 'Black', 0)).label, 'Black is checkmated');
  assert.equal(engineEvaluation(engine(150, 'White', null, 'lower')).value, '≥ +1.50');
  assert.equal(engineEvaluation(engine(-20, 'White', null, 'upper')).label, 'Upper bound');
});

test('missing engine evidence is not presented as a zero evaluation', () => {
  assert.equal(engineEvaluation(null), null);
  assert.equal(engineEvaluation({}), null);
  assert.equal(engineEvaluation(engine(null)), null);
  assert.equal(engineEvaluation(engine(NaN)), null);
});

test('candidate evaluations use their own scores while retaining the played-move score and perspective', () => {
  const evidence = engine(-73);
  const candidate = { ...evidence.played_move, uci: 'd6d5', san: 'd5', rank: 1, score: { cp: 4, mate: null, bound: 'exact' } };
  assert.equal(engineEvaluation(evidence).value, '−0.73');
  assert.deepEqual(engineEvaluation(evidence, candidate), { value: '+0.04', tone: 'neutral', label: 'Approximately level', perspective: 'Black' });
  assert.equal(engineEvaluation(evidence).value, '−0.73');
  assert.equal(engineEvaluation(evidence, { ...candidate, score: { cp: null, mate: 2, bound: 'exact' } }).label, 'Black has mate in 2');
  assert.equal(engineEvaluation(evidence, { ...candidate, score: { cp: null, mate: null, bound: 'exact' } }), null);
});
