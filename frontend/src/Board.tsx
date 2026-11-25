import { useEffect, useId, useState } from 'react';
import type { CandidateMove, Position } from './types';
import { squareCenter } from './boardAnnotations';

const names: Record<string, string> = { p: 'pawn', r: 'rook', n: 'knight', b: 'bishop', q: 'queen', k: 'king' };

// Locally bundled Classic pieces match the user's supplied reference.
// Asset sources and ownership are recorded in public/assets/chess/SOURCES.json.
export function Piece({ piece }: { piece: string }) {
  const color = piece === piece.toUpperCase() ? 'w' : 'b';
  return <img className="piece" src={`/assets/chess/classic/${color}${piece.toLowerCase()}.png`} alt="" aria-hidden="true" width={150} height={150} draggable={false}/>;
}

// Keep the existing wordmark independent of the board's selected piece theme.
export function BrandKnight() {
  return <svg viewBox="0 0 48 48" aria-hidden="true" className="brand-glyph" fill="#fffdf5" stroke="#344b5d" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round">
    <path d="M15 34c0-8 11-8 12-17l-8 6-7-1-2-5L22 7l5 2 5-3v7c8 7 7 15 4 21z"/>
    <path d="M14 34h23v6H14z"/><path d="m24 10-1 4M14 17l3 1"/>
    <circle cx="24" cy="16" r="1.2" fill="#344b5d" stroke="none"/>
  </svg>;
}

export default function Board({ position, flipped, candidate, candidateName, annotationLabel = 'Candidate', legalMoves, onMove, inputDisabled = false }: {
  position: Position; flipped: boolean; candidate?: CandidateMove; candidateName?: string; annotationLabel?: string;
  legalMoves?: string[]; onMove?: (uci: string) => void; inputDisabled?: boolean;
}) {
  const arrowId = useId();
  const [selected, setSelected] = useState<string | null>(null);
  const [promotion, setPromotion] = useState<string[]>([]);
  useEffect(() => { setSelected(null); setPromotion([]); }, [position.fen, inputDisabled]);
  const targets = (legalMoves ?? []).filter(move => move.slice(0, 2) === selected);
  function chooseSquare(square: string) {
    if (inputDisabled || !onMove || promotion.length) return;
    const moves = targets.filter(move => move.slice(2, 4) === square);
    if (moves.length > 1) { setPromotion(moves); return; }
    if (moves.length === 1) { setSelected(null); onMove(moves[0]); return; }
    setSelected(selected !== square && legalMoves?.some(move => move.startsWith(square)) ? square : null);
  }
  const origin = candidate ? squareCenter(candidate.uci.slice(0, 2), flipped) : null;
  const destination = candidate ? squareCenter(candidate.uci.slice(2, 4), flipped) : null;
  const squares: Record<string, string> = {};
  position.fen.split(' ')[0].split('/').forEach((rank, y) => {
    let x = 0;
    for (const piece of rank) {
      if (/\d/.test(piece)) x += Number(piece);
      else squares[`${'abcdefgh'[x++]}${8 - y}`] = piece;
    }
  });
  const files = (flipped ? 'hgfedcba' : 'abcdefgh').split('');
  const ranks = flipped ? [1, 2, 3, 4, 5, 6, 7, 8] : [8, 7, 6, 5, 4, 3, 2, 1];
  const summary = Object.entries(squares).map(([square, p]) => `${p === p.toUpperCase() ? 'White' : 'Black'} ${names[p.toLowerCase()]} ${square}`).join(', ');
  return <><div className="board" role={onMove ? 'group' : 'img'} aria-label={`Chessboard. ${flipped ? 'Black' : 'White'} at bottom. ${candidate ? `${annotationLabel} ${candidateName ?? candidate.uci}: arrow from ${candidate.uci.slice(0, 2)} to ${candidate.uci.slice(2, 4)}; highlights ${candidate.highlight_squares.join(' and ')}. ${candidate.reason} ` : ''}${onMove ? 'Select a piece, then its destination.' : summary}`}>
    {ranks.flatMap((rank, y) => files.map((file, x) => {
      const square = `${file}${rank}`;
      const Square = onMove ? 'button' : 'div';
      const piece = squares[square];
      const target = targets.some(move => move.slice(2, 4) === square);
      return <Square key={square} type={onMove ? 'button' : undefined} disabled={onMove ? inputDisabled : undefined}
        aria-label={onMove ? `${square}${piece ? `, ${piece === piece.toUpperCase() ? 'White' : 'Black'} ${names[piece.toLowerCase()]}` : ', empty'}${target ? ', legal destination' : ''}` : undefined}
        aria-pressed={onMove ? selected === square : undefined} onClick={onMove ? () => chooseSquare(square) : undefined}
        style={{ backgroundPosition: `${x * 100 / 7}% ${y * 100 / 7}%` }} className={`square ${(x + y) % 2 ? 'dark' : 'light'} ${position.last_move?.includes(square) ? 'last-move' : ''} ${position.check_square === square ? 'in-check' : ''} ${selected === square ? 'selected-square' : ''} ${target ? 'legal-target' : ''}`}>
        {x === 0 && <span className="rank-label">{rank}</span>}
        {y === 7 && <span className="file-label">{file}</span>}
        {squares[square] && <Piece piece={squares[square]}/>}
      </Square>;
    }))}
    {candidate && origin && destination && <svg className="board-annotations" viewBox="0 0 8 8" aria-hidden="true">
      <defs><marker id={arrowId} markerWidth=".48" markerHeight=".48" refX=".39" refY=".24" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0 L.48 .24 L0 .48 Z" fill="currentColor"/></marker></defs>
      {candidate.highlight_squares.map(square => {
        const [x, y] = squareCenter(square, flipped);
        return <rect key={square} data-square={square} x={x - .45} y={y - .45} width=".9" height=".9" rx=".03" className="candidate-square"/>;
      })}
      <line x1={origin[0]} y1={origin[1]} x2={destination[0]} y2={destination[1]} className="candidate-arrow" markerEnd={`url(#${arrowId})`}/>
    </svg>}
  </div>{promotion.length > 0 && <div className="promotion-choice" role="group" aria-label="Choose promotion piece">
    <span>Promote to</span>{promotion.map(move => <button key={move} type="button" className="secondary-button" onClick={() => { setPromotion([]); setSelected(null); onMove?.(move); }}>{names[move[4]]}</button>)}
    <button type="button" className="text-button" onClick={() => { setPromotion([]); setSelected(null); }}>Cancel</button>
  </div>}</>;
}
