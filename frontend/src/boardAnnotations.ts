import type { CoachResponse } from './types.ts';

export type CandidateSelection = { fen: string; responseId: string; uci: string };

// Coordinates in an 8 × 8 SVG, including board orientation.
export function squareCenter(square: string, flipped: boolean): [number, number] {
  const file = square.charCodeAt(0) - 97;
  const rank = Number(square[1]) - 1;
  return flipped ? [7.5 - file, rank + .5] : [file + .5, 7.5 - rank];
}

export function visibleCandidate(selection: CandidateSelection | null, response: CoachResponse | undefined, fen: string, transitioning: boolean) {
  if (transitioning || !selection || !response || response.fen !== fen || selection.fen !== fen || selection.responseId !== response.response_id) return undefined;
  return response.teaching?.candidate_moves.find(candidate => candidate.uci === selection.uci);
}
