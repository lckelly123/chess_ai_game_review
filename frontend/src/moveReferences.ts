import type { CoachMove } from './coachMoves.ts';

export type MoveReference = {text: string; move?: CoachMove};

// Parse plain text only. A token cannot create HTML, a URL, or a move outside
// the selected candidates and the original played move.
export function moveReferences(text: string, moves: CoachMove[]): MoveReference[] {
  const parts: MoveReference[] = [];
  let offset = 0;
  for (const match of text.matchAll(/\[\[([a-h][1-8][a-h][1-8][qrbn]?)\]\]/g)) {
    if (match.index > offset) parts.push({text: text.slice(offset, match.index)});
    const move = moves.find(item => item.uci === match[1]);
    parts.push(move ? {text: move.san, move} : {text: match[0]});
    offset = match.index + match[0].length;
  }
  if (offset < text.length) parts.push({text: text.slice(offset)});
  return parts;
}
