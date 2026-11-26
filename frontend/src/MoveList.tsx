import { useEffect, useRef } from 'react';
import { engineEvaluation } from './coachContent';
import { matchingReview } from './engineReview';
import type { EngineReview, Move, Position } from './types';

export default function MoveList({ moves, positions, reviews, ply, onSelect }: {
  moves: Move[]; positions: Position[]; reviews: Record<string, EngineReview>; ply: number; onSelect: (ply: number) => void;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const selected = useRef<HTMLButtonElement>(null);
  const rows = new Map<number, {white?: number; black?: number}>();
  moves.forEach((move, index) => {
    const row = rows.get(move.number) ?? {};
    if (move.color === 'white' || move.color === 'black') row[move.color] = index;
    rows.set(move.number, row);
  });
  useEffect(() => {
    const parent = scroller.current, button = selected.current;
    if (!parent || !button) return;
    const viewport = parent.getBoundingClientRect(), bounds = button.getBoundingClientRect();
    if (bounds.top < viewport.top + 36) parent.scrollTop -= viewport.top + 36 - bounds.top;
    else if (bounds.bottom > viewport.bottom) parent.scrollTop += bounds.bottom - viewport.bottom;
  }, [ply]);

  return <aside className="move-list" aria-labelledby="move-list-title">
    <div className="move-list-heading"><h2 id="move-list-title">Moves</h2><span>Eval for mover</span></div>
    <div className="move-list-scroll" ref={scroller}>
      <table>
        <thead><tr><th scope="col"><span className="visually-hidden">Move number</span></th><th scope="col">White</th><th scope="col">Black</th></tr></thead>
        <tbody>{[...rows].map(([number, row]) => <tr key={number}>
          <th scope="row">{number}.</th>
          {(['white', 'black'] as const).map(color => {
            const index = row[color], move = index === undefined ? undefined : moves[index];
            const review = move && index !== undefined ? matchingReview(move, positions[index], reviews[String(index)]) : undefined;
            const score = engineEvaluation(review?.stockfish);
            return <td key={color}>{move && index !== undefined && <button type="button" ref={ply === index ? selected : undefined}
              aria-current={ply === index ? 'step' : undefined} onClick={() => onSelect(index)}
              aria-label={`Review ${number}${color === 'white' ? '.' : '…'} ${move.san}, ${score ? `evaluation ${score.value} from ${score.perspective}’s perspective` : 'evaluation not available'}`}
              title={`Position before ${number}${color === 'white' ? '.' : '…'} ${move.san}${score ? ` · ${score.label}` : ''}`}>
              <span className="move-list-san">{move.san}</span>
              {score ? <span className={`move-list-eval ${score.tone}`}>{score.value}</span> : <span className="move-list-eval missing" aria-hidden="true">—</span>}
            </button>}</td>;
          })}
        </tr>)}</tbody>
      </table>
      {!moves.length && <p className="move-list-empty">No recorded moves.</p>}
    </div>
  </aside>;
}
