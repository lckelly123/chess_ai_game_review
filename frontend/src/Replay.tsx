import { useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { ArrowDownUp, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Info, Pause, Play, RotateCcw } from 'lucide-react';
import Board from './Board';
import MoveList from './MoveList';
import CoachCards from './CoachCards';
import PracticeCard from './PracticeCard';
import { needsPractice } from './reviewPractice';
import { useReviewPractice } from './useReviewPractice';
import type { CoachResponse, EngineReview, GameAnalysis, GameDetail } from './types';
import { api, perspective, readStored, store } from './types';
import { AUTOPLAY_TURN_MS, replayStops, replayNavigation, restoreReplay } from './replayNavigation';
import { visibleCandidate, type CandidateSelection } from './boardAnnotations';
import type { PvSequence } from './pvReferences';
import { analysisActive, analysisProgress, coachedErrorPlies, engineMoves, engineSelectionId, errorMarkers, matchingReview, mergeCoachResponses, opponentAnalysisPending, visibleEngineCandidate } from './engineReview';

const COACH_MODELS = [
  { value: 'gpt-6-astra', label: 'GPT-6 Astra' },
  { value: 'gpt-6.1-terra', label: 'GPT-6.1 Terra' },
] as const;
const coachModelLabel = (model: string) => COACH_MODELS.find(option => option.value === model)?.label ?? model;
const VARIATION_STEP_MS = 1000;
type VariationPlayback = { sequence: PvSequence; step: number; gamePly: number; responseId: string; ownerUci: string };

export default function Replay({ game, username }: { game: GameDetail; username: string }) {
  const player = perspective(game, username);
  const color = player.isWhite ? 'white' : 'black';
  const [analysis, setAnalysis] = useState<GameAnalysis | null>(() => game.engine_analyses?.[color] ?? null);
  const [analysisError, setAnalysisError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [revealedPly, setRevealedPly] = useState<number | null>(null);
  const [navigation, dispatch] = useReducer(replayNavigation, undefined, () =>
    restoreReplay(replayStops(game.positions), Number(readStored(`position:${game.id}`))));
  const { ply, playing, stops } = navigation;
  const boardPosition = game.positions[ply];
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [flipped, setFlipped] = useState(!player.isWhite);
  const [coachResponses, setCoachResponses] = useState<Record<string, CoachResponse>>(() => game.coach_responses ?? {});
  const position = game.positions[ply];
  const nextMove = game.moves[ply];
  const opponentTurn = !!nextMove && nextMove.color !== color;
  const savedResponse = coachResponses[String(ply)];
  const coachResponse = !opponentTurn && savedResponse?.fen === position.fen
    && savedResponse.played_move === (nextMove?.uci ?? null) ? savedResponse : undefined;
  const reviews = useMemo(() => {
    const result: Record<string, EngineReview> = {};
    for (const saved of Object.values(game.engine_analyses ?? {})) Object.assign(result, saved?.opponent_moves, saved?.moves);
    Object.assign(result, analysis?.opponent_moves, analysis?.moves);
    for (const [key, response] of Object.entries(coachResponses)) {
      if (!result[key] && response.stockfish && response.played_move) result[key] = {fen: response.fen, played_move: response.played_move, stockfish: response.stockfish};
    }
    return result;
  }, [game.engine_analyses, analysis, coachResponses]);
  const engineReview = matchingReview(nextMove, position, reviews[String(ply)]);
  const practiceEligible = revealedPly !== ply && needsPractice(nextMove, color, position.fen, engineReview, coachResponse);
  const practice = useReviewPractice(game.id, color, ply, position.fen, nextMove?.uci ?? '', practiceEligible, false);
  const hideReview = practice.active || !!practice.shownMove;
  const markers = errorMarkers(game.moves, game.positions, stops, reviews, color);
  const reviewPlies = coachedErrorPlies(game.moves, game.positions, reviews, coachResponses, color);
  const previousReview = reviewPlies.filter(value => value < ply).at(-1);
  const nextReview = reviewPlies.find(value => value > ply);
  const [candidateSelection, setCandidateSelection] = useState<CandidateSelection | null>(null);
  const [variation, setVariation] = useState<VariationPlayback | null>(null);
  const boardColumn = useRef<HTMLDivElement>(null);
  const candidate = hideReview ? undefined : coachResponse ? visibleCandidate(candidateSelection, coachResponse, position.fen, false)
    : visibleEngineCandidate(candidateSelection, engineReview, position.fen, false);
  const candidateName = candidate ? coachResponse?.candidate_san?.[candidate.uci]
    ?? (coachResponse?.stockfish?.played_move.uci === candidate.uci ? coachResponse.stockfish.played_move.san
      : engineMoves(engineReview).find(move => move.uci === candidate.uci)?.san ?? candidate.uci) : undefined;
  const savedAt = coachResponse ? new Date(coachResponse.created_at).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  }) : null;
  const positionLabel = ply === 0 ? 'Starting position' : `After ${game.moves[ply - 1].number}${game.moves[ply - 1].color === 'white' ? '.' : '…'} ${game.moves[ply - 1].san}`;
  const coachDetails = coachResponse ? `${positionLabel} · ${coachModelLabel(coachResponse.model)} · Saved ${savedAt}` : positionLabel;
  const playback = !hideReview && variation?.gamePly === ply && variation.responseId === coachResponse?.response_id
    && variation.ownerUci === candidate?.uci ? variation : null;
  const shownPosition = practice.shownMove?.position ?? (playback ? playback.sequence.positions[playback.step] : boardPosition);
  const turn = shownPosition.fen.split(' ')[1] === 'w' ? 'White' : 'Black';
  const top = flipped ? 'white' : 'black';
  const bottom = flipped ? 'black' : 'white';
  const seek = (value: number) => { setRevealedPly(null); setCandidateSelection(null); setVariation(null); dispatch({ type: 'seek', ply: value }); };
  const step = (direction: 1 | -1) => { setRevealedPly(null); setVariation(null); dispatch({ type: 'step', direction }); };
  const jumpReview = (value: number) => { setRevealedPly(value); setVariation(null); dispatch({ type: 'seek', ply: value }); };
  const toggleGamePlayback = () => { setVariation(null); dispatch({type: 'toggle-play'}); };

  useEffect(() => {
    setCandidateSelection(revealedPly === ply && coachResponse?.played_move
      ? {fen: position.fen, responseId: coachResponse.response_id, uci: coachResponse.played_move} : null);
    setVariation(null);
  }, [ply, revealedPly, coachResponse?.response_id]);
  useEffect(() => { if (practice.active) dispatch({type: 'pause'}); }, [practice.active, ply]);
  const originalMove = practice.active && !practice.shownMove ? nextMove : undefined;

  function selectCandidate(uci: string) {
    if ((!coachResponse && !engineReview) || hideReview) return;
    setVariation(null);
    dispatch({ type: 'pause' });
    setCandidateSelection(candidate?.uci === uci ? null : { fen: position.fen, responseId: coachResponse?.response_id ?? engineSelectionId(engineReview!), uci });
  }

  function playSequence(sequence: PvSequence) {
    if (!candidate || !coachResponse || hideReview) return;
    dispatch({type: 'pause'});
    setVariation({sequence, step: 0, gamePly: ply, responseId: coachResponse.response_id, ownerUci: candidate.uci});
    const board = boardColumn.current?.querySelector('.board');
    const bounds = board?.getBoundingClientRect();
    if (bounds && (bounds.top < 0 || bounds.bottom > window.innerHeight)) {
      board?.scrollIntoView({behavior: reducedMotion ? 'instant' : 'smooth', block: 'center'});
    }
  }

  useEffect(() => {
    if (!playback || playback.step >= playback.sequence.san.length) return;
    const timer = window.setTimeout(() => {
      // A replaced or cancelled sequence must never receive a stale timer tick.
      setVariation(current => current === playback ? {...current, step: current.step + 1} : current);
    }, VARIATION_STEP_MS);
    return () => window.clearTimeout(timer);
  }, [playback]);

  const analyzing = analysisActive(analysis);
  async function resumeAnalysis() {
    if (submitting || analyzing) return;
    setSubmitting(true); setAnalysisError('');
    try {
      setAnalysis(await api<GameAnalysis>(`/api/games/${game.id}/analysis`, {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username, model: readStored('coach-model') === 'gpt-6.1-terra' ? 'gpt-6.1-terra' : 'gpt-6-astra'})}));
    } catch (err) { setAnalysisError(err instanceof Error ? err.message : 'Could not resume analysis.'); }
    finally { setSubmitting(false); }
  }
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

  useEffect(() => { store(`position:${game.id}`, String(ply)); }, [game.id, ply]);
  useEffect(() => {
    if (!playing || practice.active) return;
    if (ply >= game.moves.length) { dispatch({ type: 'pause' }); return; }
    const timer = window.setTimeout(() => dispatch({ type: 'step', direction: 1, automatic: true }), AUTOPLAY_TURN_MS);
    return () => window.clearTimeout(timer);
  }, [playing, ply, game.moves.length, practice.active]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest('input, textarea, select, .coach-cards, .board, .promotion-choice, [contenteditable="true"]') || event.ctrlKey || event.altKey || event.metaKey) return;
      // Space keeps its native action on focused controls. Navigation keys still
      // work after using a replay button, without interrupting form controls.
      if (event.key === ' ' && target.closest('button, a')) return;
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', ' '].includes(event.key)) return;
      event.preventDefault();
      setVariation(null);
      if (event.key !== ' ') { setRevealedPly(null); setCandidateSelection(null); }
      if (event.key === ' ') { if (!practice.active) dispatch({ type: 'toggle-play' }); }
      else if (event.key === 'Home' || event.key === 'End') dispatch({ type: 'seek', ply: event.key === 'Home' ? 0 : game.moves.length });
      else dispatch({ type: 'step', direction: event.key === 'ArrowRight' ? 1 : -1 });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [game.moves.length, practice.active]);

  const playerBar = (color: 'white' | 'black') => <div className="player-bar">
    <span className={`color-token ${color}`} aria-label={`${color} pieces`}/>
    <strong>{game[color]}</strong><span className="rating">{game[`${color}_rating`] ?? 'Unrated'}</span>
  </div>;

  return <section className="replay" aria-label="Game replay">
    <div className="game-heading">
      <h1>{game.white} <span>vs</span> {game.black}</h1>
    </div>
    <div className="replay-columns">
      <div className="board-column" ref={boardColumn}>
        <MoveList moves={game.moves} positions={game.positions} reviews={reviews} ply={ply} onSelect={seek}/>
        {playerBar(top)}
        <Board position={shownPosition} flipped={flipped}
          candidate={!playback ? candidate : undefined} candidateName={candidateName} originalMove={originalMove}
          legalMoves={practice.legalMoves.map(move => move.uci)} onMove={practice.active ? uci => { dispatch({type: 'pause'}); void practice.attemptMove(uci); } : undefined}
          inputDisabled={practice.inputDisabled}/>
        {playerBar(bottom)}
        {playback && <div className="variation-playback" role="group" aria-label="Variation playback">
          <span className="variation-status" role="status">{playback.step < playback.sequence.san.length ? 'Exploring variation' : 'Variation complete'}
            <span>{playback.step === 0 ? 'Starting position' : playback.sequence.san[playback.step - 1]} · {playback.step} / {playback.sequence.san.length}</span>
          </span>
          <div className="variation-actions">
            <button type="button" className="text-button" onClick={() => setVariation(null)}>Back to game</button>
            <button type="button" className="text-button" onClick={() => playSequence(playback.sequence)}><RotateCcw size={14} aria-hidden="true"/>Replay</button>
          </div>
        </div>}
        <div className="board-controls">
          <button className="icon-button" onClick={() => setFlipped(f => !f)} title="Flip board" aria-label="Flip board"><ArrowDownUp size={19}/></button>
          <div className="transport">
            <button className="icon-button" disabled={ply === 0} onClick={() => seek(0)} title="First position (Home)" aria-label="First position"><ChevronsLeft size={21}/></button>
            <button className="icon-button" disabled={ply === 0} onClick={() => step(-1)} title="Previous move (left arrow)" aria-label="Previous move"><ChevronLeft size={22}/></button>
            <button className="play-button" disabled={practice.active} onClick={toggleGamePlayback} title="Autoplay moves (space)" aria-label={playing ? 'Pause replay' : 'Play replay'}>{playing ? <Pause size={18}/> : <Play size={18}/>}</button>
            <button className="icon-button" disabled={ply === game.moves.length} onClick={() => step(1)} title="Next move (right arrow)" aria-label="Next move"><ChevronRight size={22}/></button>
            <button className="icon-button" disabled={ply === game.moves.length} onClick={() => seek(game.moves.length)} title="Final position (End)" aria-label="Final position"><ChevronsRight size={21}/></button>
          </div>
          <span className="position-count">{ply} / {game.moves.length}</span>
        </div>
        <div className="position-timeline">
          <input className="position-slider" type="range" min={0} max={stops.length - 1} value={ply} onChange={e => seek(Number(e.target.value))} aria-label="Replay position" aria-valuetext={ply === 0 ? 'Starting position' : `After ${game.moves[ply - 1].san}, half-move ${ply}`}/>
          {markers.length > 0 && <div className="timeline-markers" role="group" aria-label="Moves to review">
            {markers.map(marker => <button key={marker.ply} type="button" className={`timeline-marker ${marker.status}`} style={{left: `${marker.percent}%`}}
              data-edge={marker.percent < 20 ? 'start' : marker.percent > 80 ? 'end' : undefined}
              aria-label={`Review ${marker.label}`} aria-current={ply === marker.ply ? 'step' : undefined}
              onClick={() => seek(marker.ply)}>
              <span className="timeline-tooltip" aria-hidden="true">{marker.label}</span>
            </button>)}
          </div>}
        </div>
        <div className="visually-hidden" aria-live="polite">{!playback && ply === game.moves.length ? `Final position · ${game.result}` : `${playback ? 'Variation · ' : practice.shownMove ? `Your attempt ${practice.shownMove.san} · ` : ''}${turn} to move${shownPosition.check_square ? ' · Check' : ''}`}</div>
      </div>
      <aside className="coach-panel" aria-labelledby="coach-title">
        <div className="coach-heading">
          <div className="coach-title-group"><h2 id="coach-title">{opponentTurn ? 'Opponent’s moves' : 'Coach'}</h2>
            <span className="coach-details" tabIndex={0} role="note" aria-label={coachDetails}>
              <Info size={14} aria-hidden="true"/><span className="coach-tooltip" aria-hidden="true">{coachDetails}</span>
            </span>
          </div>
        </div>
        {analysis && analyzing && <p className="engine-analysis-progress" role="status">{analysisProgress(analysis)}</p>}
        {opponentAnalysisPending(analysis) && !analyzing && <p className="engine-analysis-progress">Opponent evaluations are not complete.{' '}
          <button type="button" className="text-button" disabled={submitting} onClick={() => void resumeAnalysis()}>{submitting ? 'Starting…' : 'Analyze remaining moves'}</button></p>}
        {(analysisError || analysis?.error) && <p className="coach-error" role="alert">{analysisError || analysis?.error} Return to the library to resume.</p>}
        <div className="coach-result" aria-busy={analyzing && !coachResponse}>
          {practiceEligible && <PracticeCard practice={practice} original={nextMove} overview={coachResponse?.teaching?.position_overview}/>}
          {!hideReview && <CoachCards key={`${position.fen}:${coachResponse?.response_id ?? ''}`} response={coachResponse} engineReview={engineReview} engineMode={!!analysis || opponentTurn} opponent={opponentTurn} nextMove={nextMove} pending={analyzing && !coachResponse} selectedUci={candidate?.uci} onSelectCandidate={selectCandidate} transitioning={false}
            activeSequenceId={playback?.sequence.id} onPlaySequence={playSequence}/>}
          {reviewPlies.length > 0 && <nav className="coach-review-navigation" aria-label="Navigate saved coach reviews">
            <button type="button" disabled={previousReview === undefined} onClick={() => previousReview !== undefined && jumpReview(previousReview)}
              aria-label="Previous coached inaccuracy, mistake or blunder"><ChevronLeft size={22} aria-hidden="true"/><span>Previous review</span></button>
            <button type="button" disabled={nextReview === undefined} onClick={() => nextReview !== undefined && jumpReview(nextReview)}
              aria-label="Next coached inaccuracy, mistake or blunder"><span>Next review</span><ChevronRight size={22} aria-hidden="true"/></button>
          </nav>}
        </div>
      </aside>
    </div>
  </section>;
}
