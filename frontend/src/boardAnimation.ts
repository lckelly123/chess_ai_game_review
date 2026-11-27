import type { Position } from './types.ts';

export const BOARD_MOVE_MS = 300;

export type MovePreviewStep = {position: Position; animation?: {uci: string; reverse: boolean}};

// Always branch from the exact decision position, restoring captured pieces,
// castling rights and promotions before playing the chosen alternative.
export function movePreviewSteps(decision: Position, current: Position, destination: Position, uci: string, undoUci?: string): MovePreviewStep[] {
  if (current.fen === destination.fen) return [{position: destination}];
  const steps: MovePreviewStep[] = [];
  if (current.fen.split(' ')[0] !== decision.fen.split(' ')[0]) {
    steps.push({position: decision, animation: undoUci ? {uci: undoUci, reverse: true} : undefined});
  }
  steps.push({position: destination, animation: {uci, reverse: false}});
  return steps;
}

export function piecesAt(fen: string): Record<string, string> {
  const squares: Record<string, string> = {};
  fen.split(' ')[0].split('/').forEach((rank, y) => {
    let x = 0;
    for (const piece of rank) {
      if (/\d/.test(piece)) x += Number(piece);
      else squares[`${'abcdefgh'[x++]}${8 - y}`] = piece;
    }
  });
  return squares;
}

// Animate pieces at their destination, using the real before/after positions.
// Captures (including en passant) restore from the FEN; promotions undo to pawns.
export function pieceMotions(beforeFen: string, afterFen: string, uci: string, reverse = false) {
  if (beforeFen.split(' ')[0] === afterFen.split(' ')[0]) return [];
  const before = piecesAt(beforeFen), after = piecesAt(afterFen);
  const start = uci.slice(0, 2), end = uci.slice(2, 4);
  const from = reverse ? end : start, to = reverse ? start : end;
  if (!before[from] || !after[to]) return [];
  const wasWhite = before[from].toUpperCase() === before[from], isWhite = after[to].toUpperCase() === after[to];
  if (wasWhite !== isWhite) return [];
  const motions = [{from, to}];
  if (before[from].toLowerCase() === 'k' && start[0] === 'e' && ['c', 'g'].includes(end[0])) {
    const rookStart = `${end[0] === 'g' ? 'h' : 'a'}${start[1]}`;
    const rookEnd = `${end[0] === 'g' ? 'f' : 'd'}${start[1]}`;
    const rookFrom = reverse ? rookEnd : rookStart, rookTo = reverse ? rookStart : rookEnd;
    if (before[rookFrom]?.toLowerCase() === 'r' && after[rookTo] === before[rookFrom]) motions.push({from: rookFrom, to: rookTo});
  }
  return motions;
}
