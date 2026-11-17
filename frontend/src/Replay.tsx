import { useEffect, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import { ArrowDownUp, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, LoaderCircle, Pause, Play } from 'lucide-react';
import Board from './Board';
import type { CoachResponse, GameDetail } from './types';
import { api, perspective, readStored, store, timeControl } from './types';

const COACH_MODELS = [
  { value: 'gpt-6-astra', label: 'GPT-6 Astra' },
  { value: 'gpt-6.1-terra', label: 'GPT-6.1 Terra' },
] as const;
type CoachModel = typeof COACH_MODELS[number]['value'];
const coachModelLabel = (model: string) => COACH_MODELS.find(option => option.value === model)?.label ?? model;

export default function Replay({ game, username }: { game: GameDetail; username: string }) {
  const player = perspective(game, username);
  const [ply, setPly] = useState(() => {
    const saved = readStored(`position:${game.id}`);
    return Math.max(0, Math.min(Number(saved) || 0, game.moves.length));
  });
  const [flipped, setFlipped] = useState(!player.isWhite);
  const [playing, setPlaying] = useState(false);
  const [question, setQuestion] = useState(() => readStored(`coach-question:${game.id}`));
  const [coachModel, setCoachModel] = useState<CoachModel>(() =>
    COACH_MODELS.find(option => option.value === readStored('coach-model'))?.value ?? COACH_MODELS[0].value);
  const [coachResponses, setCoachResponses] = useState<Record<string, CoachResponse>>(() => game.coach_responses ?? {});
  const [pendingPly, setPendingPly] = useState<number | null>(null);
  const [coachError, setCoachError] = useState<{ ply: number; message: string } | null>(null);
  const coachRequest = useRef<AbortController | null>(null);
  const position = game.positions[ply];
  const coachResponse = coachResponses[String(ply)];
  const nextMove = game.moves[ply];
  const currentCoachError = coachError?.ply === ply ? coachError.message : null;
  const savedAt = coachResponse ? new Date(coachResponse.created_at).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  }) : null;
  const positionOnlyFeedback = !!coachResponse && !!nextMove && coachResponse.played_move === null;
  const coachStatus = pendingPly !== null
    ? pendingPly === ply
      ? `Reviewing this position${nextMove ? ` and ${nextMove.san}` : ''}. This can take a few minutes.${coachResponse ? ' The saved response remains below until this finishes.' : ''}`
      : 'Reviewing another position. Return to it to see the response.'
    : currentCoachError && coachResponse
      ? `The latest run did not complete. Showing the response saved ${savedAt}.`
      : positionOnlyFeedback
        ? `Position analysis saved ${savedAt}. No move review is saved yet. Run coach to evaluate ${nextMove.san}.`
        : coachResponse
          ? `Saved ${savedAt}.${nextMove ? ` Includes the move review for ${nextMove.san}.` : ' Position analysis only; no next recorded move.'}`
          : nextMove
            ? `Review this position and the recorded move ${nextMove.san}.`
            : 'Final position: position analysis only; no next recorded move.';
  const positionLabel = ply === 0 ? 'Starting position' : `After ${game.moves[ply - 1].number}${game.moves[ply - 1].color === 'white' ? '.' : '…'} ${game.moves[ply - 1].san}`;
  const turn = position.fen.split(' ')[1] === 'w' ? 'White' : 'Black';
  const top = flipped ? 'white' : 'black';
  const bottom = flipped ? 'black' : 'white';
  const seek = (value: number) => { setPlaying(false); setPly(Math.max(0, Math.min(value, game.moves.length))); };

  useEffect(() => { store(`position:${game.id}`, String(ply)); }, [game.id, ply]);
  useEffect(() => { store(`coach-question:${game.id}`, question); }, [game.id, question]);
  useEffect(() => { store('coach-model', coachModel); }, [coachModel]);
  useEffect(() => () => { coachRequest.current?.abort(); }, []);

  async function runCoach() {
    // Guard synchronously against double-clicks before React updates the button.
    if (coachRequest.current) return;
    const fen = position.fen;
    const requestedPly = ply;
    const playedMove = nextMove?.uci ?? null;
    const controller = new AbortController();
    coachRequest.current = controller;
    setPlaying(false);
    setPendingPly(requestedPly);
    setCoachError(null);
    try {
      const response = await api<CoachResponse>('/api/coach/analyze', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game_id: game.id, ply: requestedPly, model: coachModel }), signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        if (response.fen !== fen || response.played_move !== playedMove) throw new Error('The coach returned a different position or move. Please try again.');
        setCoachResponses(responses => ({ ...responses, [String(requestedPly)]: response }));
      }
    } catch (error) {
      if (!controller.signal.aborted) setCoachError({ ply: requestedPly, message: error instanceof Error ? error.message : 'Could not reach the coach. Please try again.' });
    } finally {
      if (!controller.signal.aborted) { coachRequest.current = null; setPendingPly(null); }
    }
  }
  useEffect(() => {
    if (!playing) return;
    if (ply >= game.moves.length) { setPlaying(false); return; }
    const timer = window.setTimeout(() => setPly(p => p + 1), 850);
    return () => window.clearTimeout(timer);
  }, [playing, ply, game.moves.length]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest('input, textarea, select, .coach-response, [contenteditable="true"]') || event.ctrlKey || event.altKey || event.metaKey) return;
      // Space keeps its native action on focused controls. Navigation keys still
      // work after using a replay button, without interrupting question typing.
      if (event.key === ' ' && target.closest('button, a')) return;
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', ' '].includes(event.key)) return;
      event.preventDefault();
      if (event.key === ' ') { if (ply === game.moves.length) setPly(0); setPlaying(p => !p); }
      else { setPlaying(false); setPly(p => event.key === 'Home' ? 0 : event.key === 'End' ? game.moves.length : Math.max(0, Math.min(game.moves.length, p + (event.key === 'ArrowRight' ? 1 : -1)))); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [ply, game.moves.length]);

  const playerBar = (color: 'white' | 'black') => <div className="player-bar">
    <span className={`color-token ${color}`} aria-label={`${color} pieces`}/>
    <strong>{game[color]}</strong><span className="rating">{game[`${color}_rating`] ?? 'Unrated'}</span>
    {game[color].toLowerCase() === username && <span className="you-label">You</span>}
  </div>;

  return <section className="replay" aria-label="Game replay">
    <div className="game-heading">
      <div><h1>{game.white} <span>vs</span> {game.black}</h1><p>{new Date(game.end_time * 1000).toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })}<span className="dot">·</span><span className="capitalize">{game.time_class}</span> {timeControl(game.time_control)}</p></div>
      <span className={`result-label ${player.result}`}>{player.result === 'win' ? 'You won' : player.result === 'loss' ? 'You lost' : 'Draw'}</span>
    </div>
    <div className="replay-columns">
      <div className="board-column">
        {playerBar(top)}
        <Board position={position} flipped={flipped}/>
        {playerBar(bottom)}
        <div className="board-controls">
          <button className="icon-button" onClick={() => setFlipped(f => !f)} title="Flip board" aria-label="Flip board"><ArrowDownUp size={19}/></button>
          <div className="transport">
            <button className="icon-button" disabled={ply === 0} onClick={() => seek(0)} title="First position (Home)" aria-label="First position"><ChevronsLeft size={21}/></button>
            <button className="icon-button" disabled={ply === 0} onClick={() => seek(ply - 1)} title="Previous move (left arrow)" aria-label="Previous move"><ChevronLeft size={22}/></button>
            <button className="play-button" onClick={() => { if (ply === game.moves.length) setPly(0); setPlaying(p => !p); }} title="Autoplay (space)" aria-label={playing ? 'Pause replay' : 'Play replay'}>{playing ? <Pause size={18}/> : <Play size={18}/>}</button>
            <button className="icon-button" disabled={ply === game.moves.length} onClick={() => seek(ply + 1)} title="Next move (right arrow)" aria-label="Next move"><ChevronRight size={22}/></button>
            <button className="icon-button" disabled={ply === game.moves.length} onClick={() => seek(game.moves.length)} title="Final position (End)" aria-label="Final position"><ChevronsRight size={21}/></button>
          </div>
          <span className="position-count">{ply} / {game.moves.length}</span>
        </div>
        <input className="position-slider" type="range" min={0} max={game.moves.length} value={ply} onChange={e => seek(Number(e.target.value))} aria-label="Replay position" aria-valuetext={ply === 0 ? 'Starting position' : `After ${game.moves[ply - 1].san}, half-move ${ply}`}/>
        <div className="position-caption" aria-live="polite">{ply === game.moves.length ? `Final position · ${game.result}` : `${turn} to move${position.check_square ? ' · Check' : ''}`}<span>{positionLabel}</span></div>
      </div>
      <aside className="coach-panel" aria-labelledby="coach-title">
        <div className="coach-heading">
          <h2 id="coach-title">Coach</h2>
          <div className="coach-actions">
            <button className="primary-button coach-run" onClick={runCoach} disabled={pendingPly !== null}>{pendingPly !== null ? <><LoaderCircle size={15} className="spin"/> Thinking…</> : <><Play size={14}/> Run coach</>}</button>
            <select className="coach-model" aria-label="OpenAI model" value={coachModel} onChange={event => setCoachModel(event.target.value as CoachModel)} disabled={pendingPly !== null}>
              {COACH_MODELS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </div>
        </div>
        <p className="coach-status" id="coach-status" role="status">{coachStatus}</p>
        {currentCoachError && <p className="coach-error" role="alert">{currentCoachError}</p>}
        <div className="coach-field" aria-busy={pendingPly === ply}>
          <div className="coach-response-label"><span id="coach-response-label">Coach response</span><span>{coachResponse && `${coachModelLabel(coachResponse.model)} · `}{positionLabel}</span></div>
          <div key={position.fen} id="coach-response" className="coach-response" role="region" tabIndex={0} aria-labelledby="coach-response-label" aria-describedby="coach-status">
            {coachResponse ? <div className="coach-prose"><Markdown skipHtml disallowedElements={['img']} components={{ h1: 'h3', h2: 'h3' }}>{coachResponse.text}</Markdown></div> : <p className="coach-placeholder">{pendingPly === ply ? 'Your coach is thinking…' : "Your coach's feedback will appear here."}</p>}
          </div>
        </div>
        <div className="coach-field">
          <label htmlFor="coach-question">Your question</label>
          <textarea id="coach-question" className="coach-question" rows={5} placeholder="Ask about this position…" value={question} onChange={event => setQuestion(event.target.value)}/>
        </div>
      </aside>
    </div>
    <p className="keyboard-tip"><span>Use <kbd>←</kbd> <kbd>→</kbd> to move through the game.</span></p>
  </section>;
}
