import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, CircleAlert, LoaderCircle, Play, RefreshCw } from 'lucide-react';
import { api } from './types';
import type { LessonAnalytics } from './lessonsData';
import './multiGameAnalysis.css';

const foundationLabels = {
  pawn_structures: 'Pawn structures', piece_play: 'Effective piece play', tactics: 'Tactical play and calculation',
  attacking: 'Attacking', defending: 'Defending', converting_advantages: 'Converting advantages', endgames: 'Endgames',
};
type Pattern = { id: string; title: string; description: string; consequence: string; thinking_adjustment: string; confidence: 'high' | 'medium' | 'low' };
type Priority = { foundation: keyof typeof foundationLabels; priority: number; reason: string; related_pattern_ids: string[]; practice_focus: string };
export type MultiGameReport = { profile_summary: string; decision_patterns: Pattern[]; foundation_priorities: Priority[] };
export type MultiGameRun = {
  id: string; username: string; status: 'queued' | 'running' | 'completed' | 'failed' | 'interrupted';
  summary: LessonAnalytics; report: MultiGameReport | null; model: string; reasoning_effort: string;
  response_id: string | null; error: string | null; created_at: string; updated_at: string;
};

const active = (run: MultiGameRun) => run.status === 'queued' || run.status === 'running';
const dateLabel = (value: string) => new Date(value).toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'});

function Report({report}: {report: MultiGameReport}) {
  return <div className="multi-game-report">
    <section aria-label="Overall assessment"><p className="multi-game-assessment">{report.profile_summary}</p></section>
    {report.decision_patterns.length > 0 && <section aria-labelledby="patterns-title">
      <h2 id="patterns-title">Decision-making patterns</h2>
      {report.decision_patterns.map(pattern => <article className="multi-game-pattern" key={pattern.id}>
        <div className="multi-game-pattern-heading"><h3>{pattern.title}</h3><span>{pattern.confidence} confidence</span></div>
        <p>{pattern.description}</p>
        <p>{pattern.consequence}</p>
        <div className="multi-game-adjustment"><h4>Try this in your next game</h4><p>{pattern.thinking_adjustment}</p></div>
      </article>)}
    </section>}
    {report.foundation_priorities.length > 0 && <section aria-labelledby="practice-title">
      <h2 id="practice-title">Foundations to develop</h2>
      <ol className="multi-game-priorities">{report.foundation_priorities.map(priority => <li key={priority.foundation}>
        <h3>{foundationLabels[priority.foundation]}</h3><p>{priority.reason}</p>
        <h4>Practice focus</h4><p>{priority.practice_focus}</p>
        <p className="multi-game-related">Addresses: {priority.related_pattern_ids.map(id =>
          report.decision_patterns.find(pattern => pattern.id === id)?.title).filter(Boolean).join(' · ')}</p>
      </li>)}</ol>
    </section>}
  </div>;
}

export default function MultiGameAnalysis({username, summary, summaryLoading, summaryError, onRefreshSummary}: {
  username: string;
  summary: LessonAnalytics | null; summaryLoading: boolean; summaryError: string; onRefreshSummary: () => void;
}) {
  const [runs, setRuns] = useState<MultiGameRun[]>([]);
  const [loading, setLoading] = useState(!!username);
  const [historyError, setHistoryError] = useState('');
  const [runError, setRunError] = useState('');
  const [posting, setPosting] = useState(false);
  const [revision, setRevision] = useState(0);
  const [selectedId, setSelectedId] = useState('');
  const mounted = useRef(true);
  const postingRef = useRef(false);
  const latestCompleted = useRef('');
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  useEffect(() => {
    if (!username) { setLoading(false); return; }
    const controller = new AbortController();
    let timer: number | undefined;
    setLoading(true); setHistoryError('');
    const load = async () => {
      try {
        const saved = await api<MultiGameRun[]>(`/api/lessons/multi-game?username=${encodeURIComponent(username)}`, {signal: controller.signal});
        if (controller.signal.aborted) return;
        setRuns(saved); setLoading(false);
        const completed = saved.find(run => run.status === 'completed');
        if (completed && completed.id !== latestCompleted.current) {
          latestCompleted.current = completed.id; setSelectedId(completed.id);
        }
        if (saved.some(active)) timer = window.setTimeout(load, 2500);
      } catch (err) {
        if (!controller.signal.aborted) { setHistoryError(err instanceof Error ? err.message : 'Could not load previous analyses.'); setLoading(false); }
      }
    };
    void load();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [username, revision]);

  const running = runs.find(active);
  const completed = runs.filter(run => run.status === 'completed' && run.report);
  const selected = completed.find(run => run.id === selectedId) || completed[0];
  const lastAttempt = runs[0];
  const canRun = !!username && !!summary?.errors.total && !summaryLoading && !summaryError && !loading && !historyError && !posting && !running;

  async function runAnalysis() {
    if (!canRun || postingRef.current) return;
    postingRef.current = true; setPosting(true); setRunError('');
    try {
      const created = await api<MultiGameRun>('/api/lessons/multi-game', {method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username})});
      if (mounted.current) setRuns(current => [created, ...current.filter(run => run.id !== created.id)]);
    } catch (err) {
      if (mounted.current) setRunError(err instanceof Error ? err.message : 'Could not start the analysis.');
    } finally {
      postingRef.current = false;
      if (mounted.current) { setPosting(false); setRevision(value => value + 1); onRefreshSummary(); }
    }
  }

  function refresh() { setRevision(value => value + 1); onRefreshSummary(); }

  return <div className="lessons-page multi-game-page">
    <a className="back-link multi-game-back" href="#lessons"><ArrowLeft size={16}/> Back to lessons</a>
    <div className="lessons-heading multi-game-heading">
      <div><h1>Multi-game analysis</h1><p>Find recurring patterns in your mistakes and choose what to practice next.</p></div>
      <div className="multi-game-actions">
        <button className="primary-button" disabled={!canRun} onClick={() => void runAnalysis()}>
          {posting || running ? <><LoaderCircle className="spin" size={16}/> {posting ? 'Starting…' : 'Analyzing…'}</> : <><Play size={16}/> Run analysis</>}
        </button>
      </div>
    </div>
    <div className="multi-game-scope">
      <div className="profile-row lessons-controls">
        <button className="icon-button" aria-label="Refresh multi-game analysis" title="Refresh multi-game analysis"
          onClick={refresh} disabled={loading || summaryLoading}><RefreshCw size={16}/></button>
      </div>
      {summaryLoading ? <p role="status">Loading analyzed games…</p> : summary && <p>
        {summary.analyzed_games.toLocaleString()} games · {summary.analyzed_moves.toLocaleString()} evaluated moves · {summary.errors.total.toLocaleString()} errors
      </p>}
    </div>
    {(summaryError || historyError) && <div className="multi-game-message error" role="alert"><CircleAlert size={18}/>
      <div><p>{summaryError || historyError}</p><button className="text-button" onClick={refresh}>Try again</button></div></div>}
    {runError && <div className="multi-game-message error" role="alert"><CircleAlert size={18}/><p>{runError}</p></div>}
    {running && <div className="multi-game-message" role="status"><LoaderCircle className="spin" size={18}/>
      <p>The coach is comparing your saved mistakes. This can take a few minutes. You can leave this screen and return to the saved response.</p></div>}
    {!running && lastAttempt && (lastAttempt.status === 'failed' || lastAttempt.status === 'interrupted') &&
      <div className="multi-game-message error" role="alert"><CircleAlert size={18}/><p>{lastAttempt.error}</p></div>}
    {!summaryLoading && !summaryError && !summary?.errors.total && <p className="multi-game-no-data">
      Analyze a game with recorded mistakes to run multi-game analysis. <a href="#games">Go to your game library</a>.
    </p>}
    {loading && !completed.length ? <p className="multi-game-loading" role="status">Loading previous responses…</p>
      : !completed.length ? !historyError && <div className="lessons-empty multi-game-empty">
        <h2>{running ? 'Your first response is on its way' : 'No coach responses yet'}</h2>
        <p>{running ? 'The completed analysis will appear here automatically.' : 'Run an analysis to connect mistakes across your games. Each response will be saved here for you to revisit.'}</p>
      </div>
      : <section className="multi-game-history" aria-labelledby="history-title">
        <div className="multi-game-history-heading"><h2 id="history-title">Coach responses</h2>
          <div><label htmlFor="multi-game-response">Saved analysis</label>
            <select id="multi-game-response" value={selected.id} onChange={event => setSelectedId(event.target.value)}>
              {completed.map((run, index) => <option key={run.id} value={run.id}>
                {dateLabel(run.created_at)}{index === 0 ? ' · Latest' : ''} · {run.summary.analyzed_games} games
              </option>)}
            </select>
          </div>
        </div>
        <p className="multi-game-response-meta">{selected.summary.analyzed_games} games · {selected.summary.analyzed_moves} evaluated moves · {selected.summary.errors.total} errors at the time of analysis</p>
        <Report key={selected.id} report={selected.report!}/>
      </section>}
  </div>;
}
