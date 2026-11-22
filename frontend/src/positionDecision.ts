import type { PositionEvidence } from './types';

const descriptions = {
  forgiving: { label: 'Forgiving', description: 'The leading moves have small weighted evaluation differences.' },
  flexible: { label: 'Flexible', description: 'The leading moves offer alternatives with moderate evaluation differences.' },
  selective: { label: 'Selective', description: 'Choosing among the leading moves has pronounced evaluation consequences.' },
  demanding: { label: 'Demanding', description: 'Large evaluation differences among the leading moves reward precise selection.' },
  critical: { label: 'Critical', description: 'Very large evaluation differences among the leading moves make selection consequential.' },
};
const unclassified = {
  terminal_position: { label: 'Game over', description: 'There is no decision to classify.' },
  single_legal_move: { label: 'Only legal move', description: 'There is no alternative move to compare.' },
  fewer_than_five_legal_moves: { label: 'Unclassified', description: 'Sharpness requires at least five legal moves.' },
  insufficient_engine_evidence: { label: 'Unclassified', description: 'Five complete engine evaluations are needed to calculate sharpness.' },
};

export function positionDecision(evidence?: PositionEvidence | null) {
  if (!evidence) return undefined;
  const tag = evidence.decision_classification;
  const score = evidence.sharpness?.score;
  if (evidence.sharpness?.version === 2 && tag && descriptions[tag] && typeof score === 'number'
      && Number.isFinite(score) && score >= 0 && score <= 100 && !evidence.unclassified_reason) {
    const decision = descriptions[tag];
    return { ...decision, className: tag,
      tooltip: `${decision.description} Sharpness: ${score.toFixed(2)}/100, calculated from Stockfish's top five moves. This measures evaluation differences, not how difficult a move is to find.` };
  }
  const reason = evidence.unclassified_reason;
  const decision = reason && unclassified[reason] ? unclassified[reason] : unclassified.insufficient_engine_evidence;
  return { ...decision, className: 'unclassified', tooltip: decision.description };
}
