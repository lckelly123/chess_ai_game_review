import type { CoachMove } from './coachMoves.ts';
import type { CandidateSelection } from './boardAnnotations.ts';
import type { CoachResponse, EngineReview, GameAnalysisSummary, Move, MoveQuality, Position } from './types.ts';

export const qualityLabels: Record<MoveQuality, string> = {good: 'Good', inaccuracy: 'Inaccuracy', mistake: 'Mistake', blunder: 'Blunder', uncertain: 'Quality uncertain'};
export const analysisActive = (analysis?: GameAnalysisSummary | null) => analysis?.status === 'queued' || analysis?.status === 'running';
export const coachingPending = (analysis?: GameAnalysisSummary | null) => (analysis?.coach_completed ?? 0) < (analysis?.coach_total ?? 0);

export function analysisProgress(analysis: GameAnalysisSummary) {
  if (analysis.status === 'queued') return `Queued · ${analysis.completed}/${analysis.total} moves`;
  if (analysis.completed === analysis.total && coachingPending(analysis)) {
    const progress = `${analysis.coach_completed}/${analysis.coach_total} flagged moves`;
    if (analysis.status === 'running') return `Coaching ${progress}`;
    if (analysis.status === 'completed') return `${analysis.completed} moves analyzed · Coach reviews pending`;
    return `Coaching paused · ${progress}`;
  }
  if (analysis.status === 'running') return `Analyzing ${analysis.completed}/${analysis.total} moves`;
  if (analysis.status === 'completed') return `${analysis.completed} moves analyzed${analysis.coach_completed ? ` · ${analysis.coach_completed} coach reviews saved` : ''}`;
  return `Paused · ${analysis.completed}/${analysis.total} moves`;
}

export function mergeCoachResponses(current: Record<string, CoachResponse>, incoming: Record<string, CoachResponse>) {
  const merged = {...current};
  for (const [ply, response] of Object.entries(incoming)) {
    if (!merged[ply] || Date.parse(response.created_at) >= Date.parse(merged[ply].created_at)) merged[ply] = response;
  }
  return merged;
}

export function engineMoves(review?: EngineReview): CoachMove[] {
  if (!review) return [];
  const top = (review.stockfish.top_moves ?? []).slice(0, 3);
  const moves = top.some(move => move.uci === review.played_move) ? top : [...top, review.stockfish.played_move];
  return moves.map(move => ({
    uci: move.uci, san: move.san, reason: '', isPlayed: move.uci === review.played_move,
    engineMove: move.uci === review.played_move ? review.stockfish.played_move : move,
    highlight_squares: [move.uci.slice(0, 2), move.uci.slice(2, 4)],
  }));
}

export const engineSelectionId = (review: EngineReview) => `engine:${review.fen}:${review.played_move}`;

export function visibleEngineCandidate(selection: CandidateSelection | null, review: EngineReview | undefined, fen: string, transitioning: boolean) {
  if (transitioning || !selection || !review || review.fen !== fen || selection.fen !== fen || selection.responseId !== engineSelectionId(review)) return undefined;
  return engineMoves(review).find(move => move.uci === selection.uci);
}

export function errorMarkers(moves: Move[], positions: Position[], stops: number[], reviews: Record<string, EngineReview>, color: 'white' | 'black') {
  return moves.flatMap((move, ply) => {
    const review = reviews[String(ply)];
    const status = review?.stockfish.move_quality?.status;
    const index = stops.indexOf(ply);
    if (move.color !== color || !review || review.fen !== positions[ply]?.fen || review.played_move !== move.uci
        || !status || !['inaccuracy', 'mistake', 'blunder'].includes(status) || index < 0) return [];
    return [{ply, status, percent: stops.length > 1 ? index * 100 / (stops.length - 1) : 0,
      label: `${move.number}${move.color === 'white' ? '.' : '…'} ${move.san} — ${qualityLabels[status]}`}];
  });
}
