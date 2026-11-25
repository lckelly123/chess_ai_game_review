import type { CoachResponse, EngineReview, TacticClassification, TacticMotif } from './types.ts';

const motifLabels: Record<TacticMotif, string> = {
  fork: 'fork', hanging_piece: 'hanging piece', skewer: 'skewer',
  discovered_attack: 'discovered attack / check', pin: 'pin', double_check: 'double check',
};

export function tacticSummary(response?: CoachResponse, review?: EngineReview): string | null {
  const fen = response?.fen ?? review?.fen;
  const played = response?.played_move ?? review?.played_move;
  if (!fen || !played) return null;
  const matches = (value?: TacticClassification) => value?.version === 1 && value.fen === fen && value.played_move === played;
  const fromCoach = response?.stockfish?.tactic_classification;
  const fromEngine = review?.stockfish.tactic_classification;
  const result = matches(fromCoach) ? fromCoach : matches(fromEngine) ? fromEngine : undefined;
  if (!result) return 'Not yet analysed';
  if (result.status === 'not_applicable') return 'No error to classify';
  const findings = result.lines.flatMap(line => {
    const labels = [...new Set(line.motifs)].map(motif => motifLabels[motif]).filter(Boolean);
    return labels.length ? [`${line.direction === 'missed' ? 'Missed' : 'Allowed'}: ${labels.join(', ')}`] : [];
  });
  if (findings.length) {
    return findings.join(' · ') + (result.lines.some(line => line.coverage === 'insufficient') ? ' · Partial line evidence' : '');
  }
  return result.status === 'unclassified' ? 'No supported motif found' : 'Insufficient line evidence';
}
