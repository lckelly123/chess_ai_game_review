import { useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { ArrowDownUp, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Info, Pause, Play, RotateCcw } from 'lucide-react';
import Board from './Board';
import GameOverview from './GameOverview';
import CoachCards from './CoachCards';
import PracticeCard from './PracticeCard';
import { useReviewPractice } from './useReviewPractice';
import { useMovePreview } from './useMovePreview';
import { needsPractice } from './reviewPractice';
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
  const [navigation, dispatch] = useReducer(replayNavigation, undefined, () =>
    restoreReplay(replayStops(game.positions), Number(readStored(`position:${game.id}`))));
  const { ply, playing, stops } = navigation;
  const boardPosition = game.positions[ply];
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [flipped, setFlipped] = useState(!player.isWhite);
  const [coachResponses, setCoachResponses] = useState<Record<string, CoachResponse>>(() => game.coach_responses ?? {});
  // Replay selects a completed move. Saved analysis is keyed by its pre-move ply.
  const reviewPly = ply - 1;
  const position = game.positions[Math.max(0, reviewPly)];
  const playedMove = game.moves[reviewPly];
  const opponentMove = !!playedMove && playedMove.color !== color;
  const savedResponse = coachResponses[String(reviewPly)];
  const coachResponse = !opponentMove && playedMove && savedResponse?.fen === position.fen
    && savedResponse.played_move === playedMove.uci ? savedResponse : undefined;
  const reviews = useMemo(() => {
    const result: Record<string, EngineReview> = {};
    for (const saved of Object.values(game.engine_analyses ?? {})) Object.assign(result, saved?.opponent_moves, saved?.moves);
    Object.assign(result, analysis?.opponent_moves, analysis?.moves);
    for (const [key, response] of Object.entries(coachResponses)) {
      if (!result[key] && response.stockfish && response.played_move) result[key] = {fen: response.fen, played_move: response.played_move, stockfish: response.stockfish, position_evidence: response.position_evidence};
    }
    return result;
  }, [game.engine_analyses, analysis, coachResponses]);
  const engineReview = matchingReview(playedMove, position, reviews[String(reviewPly)]);
  const speechId = `${game.id}:${reviewPly}:${coachResponse?.response_id ?? position.fen}:reset-${game.analysis_revision ?? 0}`;
  const markers = errorMarkers(game.moves, game.positions, stops, reviews, color);
  const reviewPlies = coachedErrorPlies(game.moves, game.positions, reviews, coachResponses, color);
  const previousReview = reviewPlies.filter(value => value < ply).at(-1);
  const nextReview = reviewPlies.find(value => value > ply);
  const practiceEligible = needsPractice(playedMove, color, position.fen, engineReview, coachResponse);
  const practice = useReviewPractice(game.id, color, reviewPly, position.fen, playedMove?.uci ?? '', practiceEligible, false, reducedMotion, game.analysis_revision ?? 0);
  const [candidateSelection, setCandidateSelection] = useState<CandidateSelection | null>(() => coachResponse?.played_move
    ? {fen: position.fen, responseId: coachResponse.response_id, uci: coachResponse.played_move}
    : engineReview ? {fen: position.fen, responseId: engineSelectionId(engineReview), uci: engineReview.played_move} : null);
  const [variation, setVariation] = useState<VariationPlayback | null>(null);
  const preview = useMovePreview(`${game.id}:${ply}:${position.fen}:${coachResponse?.response_id ?? (engineReview ? engineSelectionId(engineReview) : '')}:${practice.inPractice}`, reducedMotion);
  const boardColumn = useRef<HTMLDivElement>(null);
  const candidate = coachResponse ? visibleCandidate(candidateSelection, coachResponse, position.fen, practice.inPractice)
    : visibleEngineCandidate(candidateSelection, engineReview, position.fen, practice.inPractice);
  const candidateName = candidate ? coachResponse?.candidate_san?.[candidate.uci]
    ?? (coachResponse?.stockfish?.played_move.uci === candidate.uci ? coachResponse.stockfish.played_move.san
      : engineMoves(engineReview).find(move => move.uci === candidate.uci)?.san ?? candidate.uci) : undefined;
  const savedAt = coachResponse ? new Date(coachResponse.created_at).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  }) : null;
  const positionLabel = ply === 0 ? 'Starting position' : `After ${game.moves[ply - 1].number}${game.moves[ply - 1].color === 'white' ? '.' : '…'} ${game.moves[ply - 1].san}`;
  const coachDetails = coachResponse ? `${positionLabel} · ${coachModelLabel(coachResponse.model)} · Saved ${savedAt}` : positionLabel;
  const playback = variation?.gamePly === ply && variation.responseId === coachResponse?.response_id
    && variation.ownerUci === candidate?.uci ? variation : null;
  // Practice starts before the error; the review opens only after undo and replay.
  const boardCandidate = candidate?.uci !== playedMove?.uci ? candidate : undefined;
  const beforeError = practice.inPractice && practice.phase !== 'replaying' && !practice.shownMove;
  const shownPosition = practice.shownMove?.position ?? (beforeError ? position
    : playback ? playback.sequence.positions[playback.step] : preview.frame?.position ?? boardPosition);
  const onMainLine = !boardCandidate && !playback && !practice.shownMove && !preview.reverting;
  const errorMove = practiceEligible && !boardCandidate && !playback ? playedMove : undefined;
  const statistics = analysis?.statistics ?? Object.values(game.engine_analyses ?? {}).find(saved => saved?.statistics?.complete)?.statistics;
  const turn = shownPosition.fen.split(' ')[1] === 'w' ? 'White' : 'Black';
  const top = flipped ? 'white' : 'black';
  const bottom = flipped ? 'black' : 'white';
  const seek = (value: number) => { preview.clear(); setCandidateSelection(null); setVariation(null); dispatch({ type: 'seek', ply: value }); };
  const step = (direction: 1 | -1) => { preview.clear(); setCandidateSelection(null); setVariation(null); dispatch({ type: 'step', direction }); };
  const toggleGamePlayback = () => { preview.clear(); if (boardCandidate) setCandidateSelection(null); setVariation(null); dispatch({type: 'toggle-play'}); };

  useEffect(() => {
    setCandidateSelection(coachResponse?.played_move
      ? {fen: position.fen, responseId: coachResponse.response_id, uci: coachResponse.played_move}
      : engineReview ? {fen: position.fen, responseId: engineSelectionId(engineReview), uci: engineReview.played_move} : null);
    setVariation(null);
  }, [ply, coachResponse?.response_id, engineReview?.fen, engineReview?.played_move, practice.inPractice]);

  useEffect(() => { if (practice.inPractice) dispatch({type: 'pause'}); }, [practice.inPractice]);

  function selectCandidate(uci: string) {
    if (!coachResponse && !engineReview) return;
    const selected = candidate?.uci === uci ? null : uci;
    const targetUci = selected ?? playedMove?.uci;
    const destination = targetUci === playedMove?.uci ? boardPosition
      : targetUci ? coachResponse?.candidate_positions?.[targetUci]
        ?? coachResponse?.move_lines?.[targetUci]?.positions[1]
        ?? engineReview?.candidate_positions?.[targetUci] : undefined;
    if (targetUci && destination) {
      // Switching alternatives undoes the currently shown root. During an undo
      // the decision position is already current, so no stale move is replayed.
      preview.play(position, shownPosition, destination, targetUci,
        playback ? undefined : preview.uci ?? playedMove?.uci);
    } else preview.clear();
    setVariation(null);
    dispatch({ type: 'pause' });
    setCandidateSelection(selected ? { fen: position.fen, responseId: coachResponse?.response_id ?? engineSelectionId(engineReview!), uci: selected } : null);
  }

  function playSequence(sequence: PvSequence, restart = false) {
    if (!candidate || !coachResponse) return;
    // Continue from the displayed position without undoing moves already shown.
    // Keeping the same FEN also lets an in-flight piece animation finish.
    const step = restart ? 0 : Math.max(0, sequence.positions.findIndex(position => position.fen === shownPosition.fen));
    preview.clear();
    dispatch({type: 'pause'});
    setVariation({sequence, step, gamePly: ply, responseId: coachResponse.response_id, ownerUci: candidate.uci});
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
    if (!playing || practice.inPractice) return;
    if (ply >= game.moves.length) { dispatch({ type: 'pause' }); return; }
    const timer = window.setTimeout(() => dispatch({ type: 'step', direction: 1, automatic: true }), AUTOPLAY_TURN_MS);
    return () => window.clearTimeout(timer);
  }, [playing, ply, game.moves.length, practice.inPractice]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest('input, textarea, select, .coach-cards, .board, .promotion-choice, [contenteditable="true"]') || event.ctrlKey || event.altKey || event.metaKey) return;
      // Space keeps its native action on focused controls. Navigation keys still
      // work after using a replay button, without interrupting form controls.
      if (event.key === ' ' && target.closest('button, a')) return;
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', ' '].includes(event.key)) return;
      event.preventDefault();
      if (event.key === ' ' && practice.inPractice) return;
      preview.clear();
      setVariation(null);
      if (event.key !== ' ' || boardCandidate) setCandidateSelection(null);
      if (event.key === ' ') dispatch({ type: 'toggle-play' });
      else if (event.key === 'Home' || event.key === 'End') dispatch({ type: 'seek', ply: event.key === 'Home' ? 0 : game.moves.length });
      else dispatch({ type: 'step', direction: event.key === 'ArrowRight' ? 1 : -1 });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [game.moves.length, boardCandidate?.uci, practice.inPractice]);

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
        <GameOverview game={game} reviews={reviews} statistics={statistics} ply={ply} onSelect={seek} response={coachResponse}
          positionPly={beforeError ? reviewPly : ply} onMainLine={onMainLine} analyzing={analyzing} submitting={submitting} onComplete={() => void resumeAnalysis()}/>
        {playerBar(top)}
        <Board position={shownPosition} flipped={flipped}
          showLastMove={!boardCandidate && !preview.reverting} playedMove={onMainLine && !beforeError ? playedMove : undefined}
          errorMove={errorMove} showErrorArrow={beforeError} animation={practice.animation ?? preview.frame?.animation} reducedMotion={reducedMotion}
          legalMoves={practice.legalMoves.map(move => move.uci)} onMove={practice.inPractice ? practice.attemptMove : undefined} inputDisabled={practice.inputDisabled}/>
        {playerBar(bottom)}
        {playback && <div className="variation-playback" role="group" aria-label="Variation playback">
          <span className="variation-status" role="status">{playback.step < playback.sequence.san.length ? 'Exploring variation' : 'Variation complete'}
            <span>{playback.step === 0 ? 'Starting position' : playback.sequence.san[playback.step - 1]} · {playback.step} / {playback.sequence.san.length}</span>
          </span>
          <div className="variation-actions">
            <button type="button" className="text-button" onClick={() => {
              preview.clear(); setVariation(null);
              setCandidateSelection(coachResponse?.played_move ? {fen: position.fen, responseId: coachResponse.response_id, uci: coachResponse.played_move} : null);
            }}>Back to game</button>
            <button type="button" className="text-button" onClick={() => playSequence(playback.sequence, true)}><RotateCcw size={14} aria-hidden="true"/>Replay</button>
          </div>
        </div>}
        <div className="board-controls">
          <button className="icon-button" onClick={() => setFlipped(f => !f)} title="Flip board" aria-label="Flip board"><ArrowDownUp size={19}/></button>
          <div className="transport">
            <button className="icon-button" disabled={ply === 0} onClick={() => seek(0)} title="First position (Home)" aria-label="First position"><ChevronsLeft size={21}/></button>
            <button className="icon-button" disabled={ply === 0} onClick={() => step(-1)} title="Previous move (left arrow)" aria-label="Previous move"><ChevronLeft size={22}/></button>
            <button className="play-button" disabled={practice.inPractice} onClick={toggleGamePlayback} title="Autoplay moves (space)" aria-label={playing ? 'Pause replay' : 'Play replay'}>{playing ? <Pause size={18}/> : <Play size={18}/>}</button>
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
        <div className="visually-hidden" aria-live="polite">{practice.inPractice
          ? `${practice.phase === 'reverting' ? 'Undoing your better move' : practice.phase === 'replaying' ? `Replaying your original move ${playedMove?.san}` : practice.shownMove ? `Trying ${practice.shownMove.san}` : `Before ${playedMove?.san}. Find a better move`} · ${turn} to move`
          : onMainLine ? `${positionLabel} · ${ply === game.moves.length ? `Final position · ${game.result}` : `${turn} to move${shownPosition.check_square ? ' · Check' : ''}`}` : `${playback ? 'Variation' : `Candidate ${candidateName}`} · ${turn} to move${shownPosition.check_square ? ' · Check' : ''}`}</div>
      </div>
      <aside className="coach-panel" aria-labelledby="coach-title">
        <div className="coach-heading">
          <div className="coach-title-group"><h2 id="coach-title">{opponentMove ? 'Opponent’s moves' : 'Coach'}</h2>
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
          {playedMove ? practice.inPractice ? <PracticeCard key={speechId} practice={practice} original={playedMove}
            overview={coachResponse?.teaching?.position_overview} speechId={speechId} reducedMotion={reducedMotion}/>
          : <div key={speechId} className={practice.justCompleted ? 'coach-review-reveal' : undefined}><div>
            <CoachCards response={coachResponse} engineReview={engineReview} engineMode={!!analysis || opponentMove} opponent={opponentMove} reviewedMove={playedMove} pending={analyzing && !coachResponse} selectedUci={candidate?.uci} onSelectCandidate={selectCandidate} transitioning={false}
              speechId={speechId} reducedMotion={reducedMotion} activeSequenceId={playback?.sequence.id} onPlaySequence={playSequence}/>
          </div></div> : <p className="coach-placeholder">Play a move to see its review.</p>}
          {reviewPlies.length > 0 && <nav className="coach-review-navigation" aria-label="Navigate saved coach reviews">
            <button type="button" disabled={previousReview === undefined} onClick={() => previousReview !== undefined && seek(previousReview)}
              aria-label="Previous coached inaccuracy, mistake or blunder"><ChevronLeft size={22} aria-hidden="true"/><span>Previous review</span></button>
            <button type="button" disabled={nextReview === undefined} onClick={() => nextReview !== undefined && seek(nextReview)}
              aria-label="Next coached inaccuracy, mistake or blunder"><span>Next review</span><ChevronRight size={22} aria-hidden="true"/></button>
          </nav>}
        </div>
      </aside>
    </div>
  </section>;
}
