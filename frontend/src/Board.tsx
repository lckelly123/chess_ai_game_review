import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import type { Move, Position } from './types';
import { squareCenter } from './boardAnnotations';
import { useBoardSound } from './useBoardSound';
import { BOARD_MOVE_MS, boardPieceMotions, piecesAt } from './boardAnimation';

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

export default function Board({ position, flipped, playedMove, showLastMove = true, errorMove, showErrorArrow = false, animation, reducedMotion = false, legalMoves, onMove, inputDisabled = false }: {
  position: Position; flipped: boolean; playedMove?: Move; showLastMove?: boolean;
  legalMoves?: string[]; onMove?: (uci: string) => void; inputDisabled?: boolean;
  errorMove?: Move; showErrorArrow?: boolean; animation?: {uci: string; reverse: boolean}; reducedMotion?: boolean;
}) {
  useBoardSound(position.fen);
  const board = useRef<HTMLDivElement>(null);
  const previous = useRef({fen: position.fen, flipped, reducedMotion});
  const running = useRef(new Map<string, {movement: Animation; piece: HTMLElement; dx: number; dy: number}>());
  useLayoutEffect(() => () => {
    for (const {movement, piece} of running.current.values()) { movement.cancel(); piece.style.zIndex = ''; }
    running.current.clear();
  }, []);
  useLayoutEffect(() => {
    const before = previous.current;
    previous.current = {fen: position.fen, flipped, reducedMotion};
    // Clearing a preview or receiving a grading result must not cut short a move.
    if (before.fen === position.fen && before.flipped === flipped && before.reducedMotion === reducedMotion) return;
    if (!board.current) return;
    const motions = boardPieceMotions(before.fen, position.fen, animation);
    const beforePieces = piecesAt(before.fen), afterPieces = piecesAt(position.fen);
    const offsets = new Map<string, {dx: number; dy: number}>();
    for (const [square, active] of running.current) {
      const progress = active.movement.effect?.getComputedTiming().progress ?? 0;
      offsets.set(square, {dx: active.dx * (1 - progress), dy: active.dy * (1 - progress)});
      const currentPiece = board.current.querySelector(`[data-square="${square}"] .piece`);
      // Let unrelated moves finish while another piece starts moving.
      if (!reducedMotion && before.flipped === flipped && currentPiece === active.piece && beforePieces[square] === afterPieces[square]
        && !motions.some(motion => motion.from === square || motion.to === square)) continue;
      active.movement.cancel();
      active.piece.style.zIndex = '';
      running.current.delete(square);
    }
    if (reducedMotion || before.flipped !== flipped) return;
    const size = board.current.getBoundingClientRect().width / 8;
    for (const {from, to} of motions) {
      const piece = board.current.querySelector<HTMLElement>(`[data-square="${to}"] .piece`);
      if (!piece?.animate) continue;
      const [x1, y1] = squareCenter(from, flipped), [x2, y2] = squareCenter(to, flipped);
      const offset = offsets.get(from);
      const dx = x1 - x2 + (offset?.dx ?? 0), dy = y1 - y2 + (offset?.dy ?? 0);
      piece.style.zIndex = '2';
      const movement = piece.animate([{transform: `translate(${dx * size}px, ${dy * size}px)`}, {transform: 'translate(0, 0)'}],
        {duration: BOARD_MOVE_MS, easing: 'cubic-bezier(0.16, 1, 0.3, 1)'});
      running.current.set(to, {movement, piece, dx, dy});
      movement.onfinish = () => {
        if (running.current.get(to)?.movement !== movement) return;
        piece.style.zIndex = '';
        running.current.delete(to);
      };
    }
  }, [position.fen, flipped, animation?.uci, animation?.reverse, reducedMotion]);
  const errorArrowId = useId();
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
  const errorFrom = errorMove?.uci.slice(0, 2), errorTo = errorMove?.uci.slice(2, 4);
  const errorOrigin = errorFrom ? squareCenter(errorFrom, flipped) : null;
  const errorDestination = errorTo ? squareCenter(errorTo, flipped) : null;
  const [lastFrom, lastTo] = showLastMove ? position.last_move ?? [] : [];
  const squares = piecesAt(position.fen);
  const files = (flipped ? 'hgfedcba' : 'abcdefgh').split('');
  const ranks = flipped ? [1, 2, 3, 4, 5, 6, 7, 8] : [8, 7, 6, 5, 4, 3, 2, 1];
  const summary = Object.entries(squares).map(([square, p]) => `${p === p.toUpperCase() ? 'White' : 'Black'} ${names[p.toLowerCase()]} ${square}`).join(', ');
  return <><div ref={board} className="board" role={onMove ? 'group' : 'img'} aria-label={`Chessboard. ${flipped ? 'Black' : 'White'} at bottom. ${errorMove ? `Original move ${errorMove.san}: from ${errorFrom} to ${errorTo}; both squares highlighted in red. ${showErrorArrow ? 'Red arrow marks the original move. ' : ''}` : lastFrom && lastTo ? `Last move${playedMove ? ` ${playedMove.san}` : ''}: from ${lastFrom} to ${lastTo}; both squares highlighted. ` : ''}${onMove ? 'Select a piece, then its destination.' : summary}`}>
    {ranks.flatMap((rank, y) => files.map((file, x) => {
      const square = `${file}${rank}`;
      const Square = onMove ? 'button' : 'div';
      const piece = squares[square];
      const target = targets.some(move => move.slice(2, 4) === square);
      return <Square key={square} data-square={square} type={onMove ? 'button' : undefined} disabled={onMove ? inputDisabled : undefined}
        aria-label={onMove ? `${square}${piece ? `, ${piece === piece.toUpperCase() ? 'White' : 'Black'} ${names[piece.toLowerCase()]}` : ', empty'}${square === errorFrom ? ', original move origin' : square === errorTo ? ', original move destination' : ''}${target ? ', legal destination' : ''}` : undefined}
        aria-pressed={onMove ? selected === square : undefined} onClick={onMove ? () => chooseSquare(square) : undefined}
        style={{ backgroundPosition: `${x * 100 / 7}% ${y * 100 / 7}%` }} className={`square ${(x + y) % 2 ? 'dark' : 'light'} ${showLastMove && !errorMove && position.last_move?.includes(square) ? 'last-move' : ''} ${position.check_square === square ? 'in-check' : ''} ${square === errorFrom || square === errorTo ? 'error-move' : ''} ${selected === square ? 'selected-square' : ''} ${target ? 'legal-target' : ''}`}>
        {x === 0 && <span className="rank-label">{rank}</span>}
        {y === 7 && <span className="file-label">{file}</span>}
        {squares[square] && <Piece piece={squares[square]}/>}
      </Square>;
    }))}
    {showErrorArrow && errorOrigin && errorDestination && <svg className="board-annotations original-move-annotation" viewBox="0 0 8 8" aria-hidden="true">
      <defs><marker id={errorArrowId} markerWidth=".3" markerHeight=".3" refX=".25" refY=".15" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0 L.3 .15 L0 .3 Z" fill="currentColor"/></marker></defs>
      <line x1={errorOrigin[0]} y1={errorOrigin[1]} x2={errorDestination[0]} y2={errorDestination[1]} className="original-move-arrow" markerEnd={`url(#${errorArrowId})`}/>
    </svg>}
  </div>{promotion.length > 0 && <div className="promotion-choice" role="group" aria-label="Choose promotion piece">
    <span>Promote to</span>{promotion.map(move => <button key={move} type="button" className="secondary-button" onClick={() => { setPromotion([]); setSelected(null); onMove?.(move); }}>{names[move[4]]}</button>)}
    <button type="button" className="text-button" onClick={() => { setPromotion([]); setSelected(null); }}>Cancel</button>
  </div>}</>;
}
