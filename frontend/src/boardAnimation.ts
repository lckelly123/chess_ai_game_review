import type { Position } from './types.ts';

export const BOARD_MOVE_MS = 300;

export type PieceMotion = {from: string; to: string};
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

// Every board update slides the pieces that changed squares. Explicit preview
// moves disambiguate identical pieces; navigation and PV playback need no hint.
// During a seek, match unchanged squares first, then the nearest identical pieces.
export function boardPieceMotions(beforeFen: string, afterFen: string, animation?: MovePreviewStep['animation']): PieceMotion[] {
  const before = piecesAt(beforeFen), after = piecesAt(afterFen);
  const removed = new Set(Object.keys(before).filter(square => before[square] !== after[square]));
  const added = new Set(Object.keys(after).filter(square => before[square] !== after[square]));
  const motions: PieceMotion[] = [];
  const take = ({from, to}: PieceMotion) => {
    if (!removed.has(from) || !added.has(to)) return;
    motions.push({from, to});
    removed.delete(from);
    added.delete(to);
  };
  const promotion = (from: string, to: string, pawn: string, piece: string) =>
    (pawn === 'P' ? from[1] === '7' && to[1] === '8' && 'QRBN'.includes(piece)
      : pawn === 'p' && from[1] === '2' && to[1] === '1' && 'qrbn'.includes(piece))
    && Math.abs(from.charCodeAt(0) - to.charCodeAt(0)) <= 1;
  const changesType = (from: string, to: string) => promotion(from, to, before[from], after[to])
    || promotion(to, from, after[to], before[from]);

  if (animation) {
    for (const motion of pieceMotions(beforeFen, afterFen, animation.uci, animation.reverse)) {
      if (before[motion.from] === after[motion.to] || changesType(motion.from, motion.to)) take(motion);
    }
  }
  const pairs = [...removed].flatMap(from => [...added].map(to => ({from, to,
    distance: (from.charCodeAt(0) - to.charCodeAt(0)) ** 2 + (Number(from[1]) - Number(to[1])) ** 2,
  }))).sort((a, b) => a.distance - b.distance);
  for (const pair of pairs) if (before[pair.from] === after[pair.to]) take(pair);
  // Promotions (and undoing them) still move across the board when no caller
  // supplies a UCI move. Captured/restored pieces are taken from the exact FEN.
  for (const pair of pairs) if (changesType(pair.from, pair.to)) take(pair);
  return motions;
}
