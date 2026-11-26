import type { CoachResponse, Position } from './types.ts';

export type PvSequence = { id: string; label: string; san: string[]; positions: Position[] };
export type PvReference = { text: string; sequence?: PvSequence };
type MoveLines = NonNullable<CoachResponse['move_lines']>;

const normalizeSan = (san: string) => san.replace(/0/g, 'O').replace(/[!?]+$/, '');

// Resolve only contiguous excerpts of backend-verified PVs. The starting FEN
// comes from the saved line, including any preceding moves omitted from prose.
function resolveSequence(label: string, lines: MoveLines, preferredUci: string): PvSequence | undefined {
  const notation = label.replace(/…/g, '...').trim();
  const prefix = notation.match(/^(?:(\d+)(\.{3}|\.)|(\.{3}))/);
  const firstTurn = prefix ? (prefix[2] === '.' ? 'w' : 'b') : undefined;
  const firstNumber = prefix?.[1] ? Number(prefix[1]) : undefined;
  const san = notation.replace(/\d+\.(?:\.\.)?/g, ' ').trim().replace(/^\.{3}/, '').trim().split(/\s+/).map(normalizeSan);
  if (!san[0]) return undefined;
  const matches: { uci: string; sequence: PvSequence }[] = [];
  for (const [uci, line] of Object.entries(lines)) {
    for (let start = 0; start + san.length <= line.san.length; start++) {
      if (!san.every((move, index) => move === normalizeSan(line.san[start + index]))) continue;
      const positions = line.positions.slice(start, start + san.length + 1);
      if (positions.length !== san.length + 1 || positions.some(position => !position?.fen)) continue;
      const fenParts = positions[0].fen.split(' ');
      if (firstTurn && fenParts[1] !== firstTurn) continue;
      if (firstNumber !== undefined && Number(fenParts[5]) !== firstNumber) continue;
      matches.push({uci, sequence: {id: `${uci}:${start}:${san.length}`, label,
        san: line.san.slice(start, start + san.length), positions}});
    }
  }
  const preferred = matches.filter(match => match.uci === preferredUci);
  const candidates = preferred.length ? preferred : matches;
  // Shared prefixes are safe; different board paths with the same notation are not.
  const paths = new Map(candidates.map(match => [match.sequence.positions.map(position => position.fen).join('\n'), match.sequence]));
  return paths.size === 1 ? paths.values().next().value : undefined;
}

export function pvReferences(text: string, lines: MoveLines = {}, preferredUci = ''): PvReference[] {
  const parts: PvReference[] = [];
  let offset = 0;
  for (const match of text.matchAll(/\[\[([^\[\]]+)\]\]/g)) {
    if (match.index > offset) parts.push({text: text.slice(offset, match.index)});
    const label = match[1].trim();
    parts.push({text: label, sequence: resolveSequence(label, lines, preferredUci)});
    offset = match.index + match[0].length;
  }
  if (offset < text.length) parts.push({text: text.slice(offset)});
  return parts;
}
