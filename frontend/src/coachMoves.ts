import type { CandidateMove, CoachResponse, EngineMove } from './types.ts';

export type CoachMove = CandidateMove & {
  san: string;
  isPlayed: boolean;
  engineMove?: EngineMove;
  feedback?: string;
};

export function playedMoveAnnotation(response: CoachResponse): CandidateMove | undefined {
  const uci = response.played_move;
  if (!uci || !/^[a-h][1-8][a-h][1-8][qrbn]?$/.test(uci)) return undefined;
  return {
    uci,
    reason: response.teaching?.move_evaluation?.explanation ?? 'Run coach again for feedback on this move.',
    highlight_squares: [uci.slice(0, 2), uci.slice(2, 4)],
  };
}

export function coachMoves(response?: CoachResponse): CoachMove[] {
  if (!response) return [];
  const played = playedMoveAnnotation(response);
  const playedEngine = response.stockfish?.played_move.uci === played?.uci ? response.stockfish?.played_move : undefined;
  const rows = (response.teaching?.candidate_moves ?? []).map(candidate => {
    const isPlayed = candidate.uci === played?.uci;
    const engineMove = (isPlayed ? playedEngine : undefined)
      ?? response.position_evidence?.top_moves.find(move => move.uci === candidate.uci)
        ?? response.stockfish?.top_moves?.find(move => move.uci === candidate.uci);
    return {
      ...candidate, isPlayed, engineMove,
      san: response.candidate_san?.[candidate.uci] ?? engineMove?.san ?? candidate.uci,
      feedback: isPlayed ? response.teaching?.move_evaluation?.explanation ?? undefined : undefined,
    };
  });
  if (played && !rows.some(move => move.isPlayed)) {
    rows.push({ ...played, isPlayed: true, engineMove: playedEngine,
      san: playedEngine?.san ?? response.candidate_san?.[played.uci] ?? played.uci, feedback: undefined });
  }
  return rows;
}
