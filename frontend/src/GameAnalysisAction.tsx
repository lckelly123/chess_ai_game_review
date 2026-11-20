import { useEffect, useRef, useState } from 'react';
import { ArrowRight, LoaderCircle } from 'lucide-react';
import { api, perspective, readStored } from './types';
import type { Game, GameAnalysis, GameAnalysisSummary, MoveQuality } from './types';
import { analysisActive, analysisProgress, coachingPending, qualityLabels } from './engineReview';

const qualities: MoveQuality[] = ['good', 'inaccuracy', 'mistake', 'blunder', 'uncertain'];

export default function GameAnalysisAction({game, username, onUpdate, onOpen}: {
  game: Game; username: string; onUpdate: (analysis: GameAnalysisSummary | null) => void; onOpen: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const request = useRef<AbortController | null>(null);
  const update = useRef(onUpdate);
  update.current = onUpdate;
  const analysis = game.analysis;
  const active = analysisActive(analysis);
  const done = analysis?.status === 'completed' && !coachingPending(analysis);
  const coachOnly = analysis?.completed === analysis?.total && coachingPending(analysis);
  const opponent = perspective(game, username).opponent;
  const path = `/api/games/${game.id}/analysis`;

  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    let timer: number;
    const poll = async () => {
      try {
        const latest = await api<GameAnalysis | null>(`${path}?username=${encodeURIComponent(username)}`, {signal: controller.signal});
        if (controller.signal.aborted) return;
        update.current(latest);
        setError('');
        if (analysisActive(latest)) timer = window.setTimeout(poll, 1500);
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : 'Could not check analysis progress.');
        timer = window.setTimeout(poll, 4000);
      }
    };
    void poll();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [active, path, username]);

  async function start() {
    if (request.current || active) return;
    const controller = new AbortController();
    request.current = controller;
    setSubmitting(true); setError('');
    try {
      const result = await api<GameAnalysis>(path, {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username, model: readStored('coach-model') === 'gpt-6.1-terra' ? 'gpt-6.1-terra' : 'gpt-6-astra'}), signal: controller.signal});
      if (!controller.signal.aborted) update.current(result);
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Could not start analysis.');
    } finally {
      if (!controller.signal.aborted) { request.current = null; setSubmitting(false); }
    }
  }

  return <>
    <div className="game-analysis-actions">
      {!done && <button type="button" className="analyze-button" onClick={start} disabled={active || submitting}
        title="Analyze your moves and coach inaccuracies, mistakes, and blunders."
        aria-label={`${coachOnly ? 'Coach flagged moves in' : analysis ? 'Resume analysis of' : 'Analyze'} game against ${opponent}`}>
        {active || submitting ? <><LoaderCircle size={13} className="spin"/> {analysis?.status === 'queued' ? 'Queued' : coachOnly ? 'Coaching…' : 'Analyzing…'}</> : coachOnly && analysis?.status === 'completed' ? 'Coach flagged moves' : analysis ? 'Resume analysis' : 'Analyze game'}
      </button>}
      <a className={done ? 'analyze-button' : 'open-game'} data-game-id={game.id} href={`#game/${game.id}?player=${encodeURIComponent(username)}`}
        aria-label={`Open game against ${opponent}`} onClick={onOpen}>{done ? 'Review game' : 'Open game'} <ArrowRight size={14}/></a>
    </div>
    {(analysis || error) && <div className="game-analysis-status">
      {analysis && <span role="status">{analysisProgress(analysis)}</span>}
      {analysis?.status === 'completed' && <span className="analysis-counts" aria-label="Move classifications">
        {qualities.filter(quality => analysis.counts[quality]).map(quality => <span key={quality} className={`analysis-count ${quality}`}>{analysis.counts[quality]} {qualityLabels[quality]}</span>)}
      </span>}
      {(error || analysis?.error) && <span className="analysis-error" role="alert">{error || analysis?.error}</span>}
    </div>}
  </>;
}
