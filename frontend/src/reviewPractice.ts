import type { CoachResponse, EngineReview, Move, MoveQuality, Position } from './types.ts';
import { acceptableQuality, qualityLabels } from './engineReview.ts';

export type PracticeMove = { uci: string; san: string; position: Position };
export type PracticeContext = { fen: string; original_move: string; legal_moves: PracticeMove[] };
export type PracticeResult = { fen: string; original_move: string; move: string; accepted: boolean;
  quality: { status: MoveQuality; winning_chances_loss_pp: number | null } };
export type PracticeAttempt = { uci: string; san: string; at: string; quality: MoveQuality | null;
  lossPp: number | null; status: 'checking' | 'graded' | 'error' };

export function needsPractice(move: Move | undefined, color: string, fen: string, engine?: EngineReview, coach?: CoachResponse) {
  if (!move || move.color !== color) return false;
  const review = engine?.fen === fen && engine.played_move === move.uci ? engine
    : coach?.fen === fen && coach.played_move === move.uci ? coach : undefined;
  return ['inaccuracy', 'mistake', 'blunder'].includes(review?.stockfish?.move_quality?.status ?? '');
}

export const practiceKey = (gameId: string, color: string, ply: number, fen: string, move: string, revision = 0) =>
  `review-practice:v1:${JSON.stringify([gameId, color, ply, fen, move, ...(revision ? [revision] : [])])}`;
export const practiceComplete = (attempts: PracticeAttempt[]) => attempts.some(attempt => attempt.status === 'graded' && acceptableQuality(attempt.quality));

export function restoreAttempts(raw: string): PracticeAttempt[] {
  try {
    const value = JSON.parse(raw);
    if (!Array.isArray(value)) return [];
    return value.filter(attempt => attempt && /^[a-h][1-8][a-h][1-8][qrbn]?$/.test(attempt.uci)
      && typeof attempt.san === 'string' && typeof attempt.at === 'string'
      && ['checking', 'graded', 'error'].includes(attempt.status)
      && (attempt.quality === null || Object.hasOwn(qualityLabels, attempt.quality)))
      .map(attempt => attempt.status === 'checking' ? {...attempt, status: 'error', quality: null} : attempt);
  } catch { return []; }
}

export function resultMatches(result: PracticeResult, fen: string, original: string, move: string) {
  return result.fen === fen && result.original_move === original && result.move === move
    && result.accepted === acceptableQuality(result.quality.status);
}
