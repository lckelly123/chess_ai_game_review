import type { EngineReview, GameDetail, GameStatistics, PositionEvaluation } from './types.ts';
import { matchingReview } from './engineReview.ts';

export const summaryGrades = ['good', 'inaccuracy', 'mistake', 'blunder'] as const;

export function statisticsReady(game: Pick<GameDetail, 'positions'>, statistics?: GameStatistics | null): statistics is GameStatistics {
  return statistics?.version === 1 && statistics.perspective === 'White' && statistics.complete
    && statistics.timeline.length === game.positions.length
    && statistics.timeline.every((point, ply) => point.ply === ply && point.fen === game.positions[ply].fen && evaluationPercent(point) != null);
}

export function overviewTimeline(game: Pick<GameDetail, 'positions' | 'moves'>, reviews: Record<string, EngineReview>, statistics?: GameStatistics | null) {
  return game.positions.map((position, ply): PositionEvaluation => {
    const cached = statistics?.version === 1 && statistics.perspective === 'White' ? statistics.timeline[ply] : undefined;
    if (cached?.ply === ply && cached.fen === position.fen && cached.status !== 'missing') return cached;
    const review = matchingReview(game.moves[ply], position, reviews[String(ply)]);
    const best = review?.stockfish.top_moves?.[0];
    const score = best?.score;
    const white = position.fen.split(' ')[1] === 'w';
    if (!score || score.bound !== 'exact' || !best?.depth || review?.stockfish.perspective !== (white ? 'White' : 'Black')
        || (score.cp == null) === (score.mate == null)) return {ply, fen: position.fen, status: 'missing'};
    return {ply, fen: position.fen, status: 'evaluated', cp: score.cp == null ? null : score.cp * (white ? 1 : -1),
      mate: score.mate == null ? null : score.mate * (white ? 1 : -1),
      mate_winner: score.mate == null ? null : (score.mate > 0) === white ? 'white' : 'black', depth: best.depth};
  });
}

export function evaluationPercent(point: PositionEvaluation): number | null {
  if (point.status === 'missing') return null;
  const cp = point.cp ?? (point.mate_winner ? (point.mate_winner === 'white' ? 1000 : -1000) : null);
  return cp === null || !Number.isFinite(cp) ? null : 100 / (1 + Math.exp(-0.00368208 * Math.max(-1000, Math.min(1000, cp))));
}

export function evaluationLabel(point?: PositionEvaluation): string {
  if (!point || point.status === 'missing') return 'Not analysed';
  if (point.mate != null) return `${point.mate_winner === 'white' ? '+' : '−'}M${Math.abs(point.mate)}`;
  return point.cp == null ? 'Not analysed' : `${point.cp > 0 ? '+' : ''}${(point.cp / 100).toFixed(2)}`;
}

export function moveTime(seconds?: number | null): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—';
  if (seconds < 60) return `${Number(seconds.toFixed(1))}s`;
  const rounded = Math.round(seconds);
  return `${Math.floor(rounded / 60)}m ${rounded % 60}s`;
}

export function overviewCounts(game: Pick<GameDetail, 'moves' | 'positions'>, reviews: Record<string, EngineReview>) {
  const empty = () => ({good: 0, inaccuracy: 0, mistake: 0, blunder: 0, analysed: 0, total: 0, uncertain: 0});
  const result = {white: empty(), black: empty()};
  game.moves.forEach((move, ply) => {
    const counts = result[move.color as 'white' | 'black'];
    counts.total++;
    const review = matchingReview(move, game.positions[ply], reviews[String(ply)]);
    const grade = review?.stockfish.move_quality?.status;
    if (grade) { counts.analysed++; counts[grade]++; }
  });
  return result;
}
