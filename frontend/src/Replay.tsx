import { useEffect, useReducer, useRef, useState } from 'react';
import { ArrowDownUp, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Info, LoaderCircle, Pause, Play } from 'lucide-react';
import Board from './Board';
import CoachCards from './CoachCards';
import type { CoachResponse, GameAnalysis, GameDetail } from './types';
import { api, perspective, readStored, store, timeControl } from './types';
import { AUTOPLAY_TURN_MS, BETWEEN_TURNS_MS, playerTurnStops, replayNavigation, restoreReplay } from './replayNavigation';
import { visibleCandidate, type CandidateSelection } from './boardAnnotations';
import { analysisActive, analysisProgress, engineMoves, engineSelectionId, errorMarkers, mergeCoachResponses, visibleEngineCandidate } from './engineReview';

const COACH_MODELS = [
  { value: 'gpt-6-astra', label: 'GPT-6 Astra' },
  { value: 'gpt-6.1-terra', label: 'GPT-6.1 Terra' },
] as const;
type CoachModel = typeof COACH_MODELS[number]['value'];
const coachModelLabel = (model: string) => COACH_MODELS.find(option => option.value === model)?.label ?? model;

export default function Replay({ game, username }: { game: GameDetail; username: string }) {
  const player = perspective(game, username);
  const color = player.isWhite ? 'white' : 'black';
  const [analysis, setAnalysis] = useState<GameAnalysis | null>(() => game.engine_analyses?.[color] ?? null);
  const [analysisError, setAnalysisError] = useState('');
  const [navigation, dispatch] = useReducer(replayNavigation, undefined, () =>
    restoreReplay(playerTurnStops(game.positions, player.isWhite), Number(readStored(`position:${game.id}`))));
  const { ply, transition, playing, stops } = navigation;
  const controlPly = transition?.to ?? ply;
  const boardPosition = game.positions[transition?.via ?? ply];
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [flipped, setFlipped] = useState(!player.isWhite);
  const [question, setQuestion] = useState(() => readStored(`coach-question:${game.id}`));
  const [coachModel, setCoachModel] = useState<CoachModel>(() =>
    COACH_MODELS.find(option => option.value === readStored('coach-model'))?.value ?? COACH_MODELS[0].value);
  const [coachResponses, setCoachResponses] = useState<Record<string, CoachResponse>>(() => game.coach_responses ?? {});
  const [pendingPly, setPendingPly] = useState<number | null>(null);
  const [coachError, setCoachError] = useState<{ ply: number; message: string } | null>(null);
  const coachRequest = useRef<AbortController | null>(null);
  const position = game.positions[ply];
  const coachResponse = coachResponses[String(ply)];
  const prepared = analysis?.moves[String(ply)];
  const engineReview = prepared?.fen === position.fen && prepared.played_move === game.moves[ply]?.uci ? prepared : undefined;
  const markers = errorMarkers(game.moves, game.positions, stops, analysis?.moves ?? {}, color);
  const [candidateSelection, setCandidateSelection] = useState<CandidateSelection | null>(null);
  const boardColumn = useRef<HTMLDivElement>(null);
  const candidate = coachResponse ? visibleCandidate(candidateSelection, coachResponse, position.fen, transition !== null)
    : visibleEngineCandidate(candidateSelection, engineReview, position.fen, transition !== null);
  const candidateName = candidate ? coachResponse?.candidate_san?.[candidate.uci]
    ?? (coachResponse?.stockfish?.played_move.uci === candidate.uci ? coachResponse.stockfish.played_move.san
      : engineMoves(engineReview).find(move => move.uci === candidate.uci)?.san ?? candidate.uci) : undefined;
  const nextMove = game.moves[ply];
  const currentCoachError = coachError?.ply === ply ? coachError.message : null;
  const savedAt = coachResponse ? new Date(coachResponse.created_at).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  }) : null;
  const coachStatus = pendingPly !== null
    ? pendingPly === ply
      ? `Reviewing this position${nextMove ? ` and ${nextMove.san}` : ''}. This can take a few minutes.${coachResponse ? ' The saved response remains below until this finishes.' : ''}`
      : 'Reviewing another position. Return to it to see the response.'
    : currentCoachError && coachResponse
      ? `The latest run did not complete. Showing the response saved ${savedAt}.`
      : '';
  const positionLabel = ply === 0 ? 'Starting position' : `After ${game.moves[ply - 1].number}${game.moves[ply - 1].color === 'white' ? '.' : '…'} ${game.moves[ply - 1].san}`;
  const coachDetails = coachResponse ? `${positionLabel} · ${coachModelLabel(coachResponse.model)} · Saved ${savedAt}` : positionLabel;
  const turn = position.fen.split(' ')[1] === 'w' ? 'White' : 'Black';
  const top = flipped ? 'white' : 'black';
  const bottom = flipped ? 'black' : 'white';
  const seek = (value: number) => dispatch({ type: 'seek', ply: value });
  const step = (direction: 1 | -1) => dispatch({ type: 'step', direction, animate: !reducedMotion });

  useEffect(() => { setCandidateSelection(null); }, [ply, transition, coachResponse?.response_id]);

  function selectCandidate(uci: string) {
    if ((!coachResponse && !engineReview) || transition) return;
    dispatch({ type: 'pause' });
    setCandidateSelection(candidate?.uci === uci ? null : { fen: position.fen, responseId: coachResponse?.response_id ?? engineSelectionId(engineReview!), uci });
    if (candidate?.uci !== uci && boardColumn.current && boardColumn.current.getBoundingClientRect().bottom < 0) {
      boardColumn.current.scrollIntoView({ behavior: reducedMotion ? 'instant' : 'smooth', block: 'start' });
    }
  }

  const analyzing = analysisActive(analysis);
  useEffect(() => {
    if (!analyzing) return;
    const controller = new AbortController();
    let timer: number;
    let savedReviews = analysis?.coach_completed ?? 0;
    const poll = async () => {
      try {
        const latest = await api<GameAnalysis | null>(`/api/games/${game.id}/analysis?username=${encodeURIComponent(username)}`, {signal: controller.signal});
        if (controller.signal.aborted) return;
        if ((latest?.coach_completed ?? 0) > savedReviews) {
          const updated = await api<GameDetail>(`/api/games/${game.id}`, {signal: controller.signal});
          if (controller.signal.aborted) return;
          setCoachResponses(current => mergeCoachResponses(current, updated.coach_responses));
          savedReviews = latest!.coach_completed;
        }
        setAnalysis(latest); setAnalysisError('');
        if (analysisActive(latest)) timer = window.setTimeout(poll, 1500);
      } catch (err) {
        if (controller.signal.aborted) return;
        setAnalysisError(err instanceof Error ? err.message : 'Could not check analysis progress.');
        timer = window.setTimeout(poll, 4000);
      }
    };
    void poll();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [analyzing, game.id, username]);

  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReducedMotion(preference.matches);
    preference.addEventListener('change', update);
    return () => preference.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    if (!transition) return;
    const timer = window.setTimeout(() => dispatch({ type: 'settle', transition }), reducedMotion ? 0 : BETWEEN_TURNS_MS);
    return () => window.clearTimeout(timer);
  }, [transition, reducedMotion]);

  useEffect(() => { store(`position:${game.id}`, String(ply)); }, [game.id, ply]);
  useEffect(() => { store(`coach-question:${game.id}`, question); }, [game.id, question]);
  useEffect(() => { store('coach-model', coachModel); }, [coachModel]);
  useEffect(() => () => { coachRequest.current?.abort(); }, []);

  async function runCoach() {
    // Guard synchronously against double-clicks before React updates the button.
    if (coachRequest.current || transition) return;
    const fen = position.fen;
    const requestedPly = ply;
    const playedMove = nextMove?.uci ?? null;
    const controller = new AbortController();
    coachRequest.current = controller;
    dispatch({ type: 'pause' });
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
    if (!playing || transition) return;
    if (ply >= game.moves.length) { dispatch({ type: 'pause' }); return; }
    const timer = window.setTimeout(() => dispatch({ type: 'step', direction: 1, animate: !reducedMotion, automatic: true }), AUTOPLAY_TURN_MS);
    return () => window.clearTimeout(timer);
  }, [playing, ply, transition, reducedMotion, game.moves.length]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest('input, textarea, select, .coach-cards, [contenteditable="true"]') || event.ctrlKey || event.altKey || event.metaKey) return;
      // Space keeps its native action on focused controls. Navigation keys still
      // work after using a replay button, without interrupting question typing.
      if (event.key === ' ' && target.closest('button, a')) return;
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', ' '].includes(event.key)) return;
      event.preventDefault();
      if (event.key === ' ') dispatch({ type: 'toggle-play' });
      else if (event.key === 'Home' || event.key === 'End') dispatch({ type: 'seek', ply: event.key === 'Home' ? 0 : game.moves.length });
      else dispatch({ type: 'step', direction: event.key === 'ArrowRight' ? 1 : -1, animate: !reducedMotion });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [reducedMotion, game.moves.length]);

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
      <div className="board-column" ref={boardColumn}>
        {playerBar(top)}
        <Board position={boardPosition} flipped={flipped} candidate={candidate} candidateName={candidateName}/>
        {candidate && <div className="board-idea" role="status"><span><strong>{candidateName}</strong>{candidate.reason && <> · {candidate.reason}</>}</span><button type="button" onClick={() => setCandidateSelection(null)}>Clear</button></div>}
        {playerBar(bottom)}
        <div className="board-controls">
          <button className="icon-button" onClick={() => setFlipped(f => !f)} title="Flip board" aria-label="Flip board"><ArrowDownUp size={19}/></button>
          <div className="transport">
            <button className="icon-button" disabled={controlPly === 0} onClick={() => seek(0)} title="First position (Home)" aria-label="First position"><ChevronsLeft size={21}/></button>
            <button className="icon-button" disabled={controlPly === 0} onClick={() => step(-1)} title="Previous turn (left arrow)" aria-label="Previous turn"><ChevronLeft size={22}/></button>
            <button className="play-button" onClick={() => dispatch({ type: 'toggle-play' })} title="Autoplay your turns (space)" aria-label={playing ? 'Pause replay' : 'Play replay'}>{playing ? <Pause size={18}/> : <Play size={18}/>}</button>
            <button className="icon-button" disabled={controlPly === game.moves.length} onClick={() => step(1)} title="Next turn (right arrow)" aria-label="Next turn"><ChevronRight size={22}/></button>
            <button className="icon-button" disabled={controlPly === game.moves.length} onClick={() => seek(game.moves.length)} title="Final position (End)" aria-label="Final position"><ChevronsRight size={21}/></button>
          </div>
          <span className="position-count">{ply} / {game.moves.length}</span>
        </div>
        <div className="position-timeline">
          <input className="position-slider" type="range" min={0} max={stops.length - 1} value={stops.indexOf(controlPly)} onChange={e => seek(stops[Number(e.target.value)])} aria-label="Replay position" aria-valuetext={controlPly === 0 ? 'Starting position' : `After ${game.moves[controlPly - 1].san}, half-move ${controlPly}`}/>
          {markers.length > 0 && <div className="timeline-markers" role="group" aria-label="Moves to review">
            {markers.map(marker => <button key={marker.ply} type="button" className={`timeline-marker ${marker.status}`} style={{left: `${marker.percent}%`}}
              data-edge={marker.percent < 20 ? 'start' : marker.percent > 80 ? 'end' : undefined}
              aria-label={`Review ${marker.label}`} aria-current={ply === marker.ply ? 'step' : undefined}
              onClick={() => seek(marker.ply)}>
              <span className="timeline-tooltip" aria-hidden="true">{marker.label}</span>
            </button>)}
          </div>}
        </div>
        {markers.length > 0 && <div className="timeline-legend" aria-label="Timeline colors"><span className="inaccuracy">Inaccuracy</span><span className="mistake">Mistake</span><span className="blunder">Blunder</span></div>}
        <div className="position-caption" aria-live="polite">{ply === game.moves.length ? `Final position · ${game.result}` : `${turn} to move${position.check_square ? ' · Check' : ''}`}<span>{positionLabel}</span></div>
      </div>
      <aside className="coach-panel" aria-labelledby="coach-title">
        <div className="coach-heading">
          <div className="coach-title-group"><h2 id="coach-title">Coach</h2>
            <span className="coach-details" tabIndex={0} role="note" aria-label={coachDetails}>
              <Info size={14} aria-hidden="true"/><span className="coach-tooltip" aria-hidden="true">{coachDetails}</span>
            </span>
          </div>
          <div className="coach-actions">
            <select className="coach-model" aria-label="OpenAI model" value={coachModel} onChange={event => setCoachModel(event.target.value as CoachModel)} disabled={pendingPly !== null}>
              {COACH_MODELS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <button className="primary-button coach-run" onClick={runCoach} disabled={pendingPly !== null || transition !== null}>{pendingPly !== null ? <><LoaderCircle size={15} className="spin"/> Thinking…</> : <><Play size={14}/> Run coach</>}</button>
          </div>
        </div>
        <p className="coach-status" id="coach-status" role="status">{coachStatus}</p>
        {analysis && analyzing && <p className="engine-analysis-progress" role="status">{analysisProgress(analysis)}</p>}
        {(analysisError || analysis?.error) && <p className="coach-error" role="alert">{analysisError || analysis?.error} Return to the library to resume.</p>}
        {currentCoachError && <p className="coach-error" role="alert">{currentCoachError}</p>}
        <div className="coach-result" aria-busy={pendingPly === ply}>
          <CoachCards key={`${position.fen}:${coachResponse?.response_id ?? ''}`} response={coachResponse} engineReview={engineReview} engineMode={!!analysis} nextMove={nextMove} pending={pendingPly === ply} selectedUci={candidate?.uci} onSelectCandidate={selectCandidate} transitioning={transition !== null}/>
        </div>
        <div className="coach-field">
          <label htmlFor="coach-question">Your question</label>
          <textarea id="coach-question" className="coach-question" rows={5} placeholder="Ask about this position…" value={question} onChange={event => setQuestion(event.target.value)}/>
        </div>
      </aside>
    </div>
    <p className="keyboard-tip"><span>Reviewing your turns as {player.isWhite ? 'White' : 'Black'}.</span><span>Use <kbd>←</kbd> <kbd>→</kbd> to step between decisions.</span></p>
  </section>;
}
