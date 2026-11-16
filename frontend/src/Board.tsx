import type { Position } from './types';

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

export default function Board({ position, flipped }: { position: Position; flipped: boolean }) {
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
  return <div className="board" role="img" aria-label={`Chessboard. ${flipped ? 'Black' : 'White'} at bottom. ${summary}`}>
    {ranks.flatMap((rank, y) => files.map((file, x) => {
      const square = `${file}${rank}`;
      return <div key={square} style={{ backgroundPosition: `${x * 100 / 7}% ${y * 100 / 7}%` }} className={`square ${(x + y) % 2 ? 'dark' : 'light'} ${position.last_move?.includes(square) ? 'last-move' : ''} ${position.check_square === square ? 'in-check' : ''}`}>
        {x === 0 && <span className="rank-label">{rank}</span>}
        {y === 7 && <span className="file-label">{file}</span>}
        {squares[square] && <Piece piece={squares[square]}/>}
      </div>;
    }))}
  </div>;
}
