import { useEffect, useState } from 'react';
import { ArrowRight, Check, ChevronRight, CircleAlert, RefreshCw } from 'lucide-react';
import { api } from './types';
import { filteredLessonRows, lessonCoverage, lessonGroupCounts, lessonSeverities, severitySummary } from './lessonsData';
import type { ErrorCounts, LessonAnalytics, LessonFilter, LessonGroup } from './lessonsData';
import './lessons.css';
import MultiGameAnalysis from './MultiGameAnalysis';

const severityLabels = { all: 'All', inaccuracy: 'Inaccuracy', mistake: 'Mistake', blunder: 'Blunder' };
const groupLabels = { positional: 'Positional', tactical: 'Tactical', unclassified: 'Unclassified' };
const tacticalCategories = [
  { key: 'tactical_miss', label: 'Missed tactics' },
  { key: 'tactical_allowed', label: 'Allowed tactics' },
] as const;

function SeverityBar({counts}: {counts: ErrorCounts}) {
  return <span className="lesson-severity-bar" aria-hidden="true">
    {lessonSeverities.filter(severity => counts[severity] > 0).map(severity =>
      <span key={severity} className={severity} style={{width: `${counts[severity] / counts.total * 100}%`}}/>
    )}
  </span>;
}

function SeverityBreakdown({counts}: {counts: ErrorCounts}) {
  return <dl className="lesson-severity-breakdown">{lessonSeverities.map(severity =>
    <div key={severity}><dt><span className={`lesson-severity-dot ${severity}`} aria-hidden="true"/>{severityLabels[severity]}</dt>
      <dd>{counts[severity].toLocaleString()}</dd></div>
  )}</dl>;
}

function LessonExplorer({data}: {data: LessonAnalytics}) {
  const groups = lessonGroupCounts(data);
  const [group, setGroup] = useState<LessonGroup>(() => groups.tactical.total > 0 ? 'tactical'
    : groups.positional.total > 0 || !groups.unclassified.total ? 'positional' : 'unclassified');
  const [tactical, setTactical] = useState<string>(() => data.categories.find(category => category.key === 'tactical_miss')?.counts.total
    ? 'tactical_miss' : 'tactical_allowed');
  const [filter, setFilter] = useState<LessonFilter>('all');
  const category = data.categories.find(item => item.key === (group === 'tactical' ? tactical : group));
  const counts = group === 'unclassified' ? data.unclassified : category?.counts;
  const matching = counts?.[filter === 'all' ? 'total' : filter] ?? 0;
  const rows = filteredLessonRows(category, filter);

  return <>
    <div className="lesson-overview" role="group" aria-label="Lesson category">
      {(['positional', 'tactical'] as const).map(key => <button key={key} type="button"
        className="lesson-overview-card" aria-pressed={group === key} aria-controls="lesson-explorer" onClick={() => setGroup(key)}>
        <span className="lesson-card-heading"><span>{groupLabels[key]}</span>
          <span className="lesson-card-selection" aria-hidden="true">{group === key && <Check size={14}/>}</span>
        </span>
        <strong className="lesson-card-count">{groups[key].total.toLocaleString()}</strong>
        <SeverityBar counts={groups[key]}/>
        <span className="lesson-card-description">{severitySummary(groups[key])}</span>
      </button>)}
    </div>
    {data.unclassified.total > 0 && <button type="button" className="lesson-unclassified"
      aria-pressed={group === 'unclassified'} aria-controls="lesson-explorer" onClick={() => setGroup('unclassified')}>
      <span>Unclassified <span className="lesson-unclassified-count">· {data.unclassified.total.toLocaleString()} {data.unclassified.total === 1 ? 'error' : 'errors'}</span></span>
      <ChevronRight size={20} aria-hidden="true"/>
    </button>}
    <section id="lesson-explorer" className="lesson-explorer" aria-labelledby="lesson-explorer-title">
      <div className="lesson-explorer-heading">
        <h2 id="lesson-explorer-title">Explore {groupLabels[group].toLowerCase()} errors</h2>
        <span role="status" aria-live="polite" aria-atomic="true">{matching.toLocaleString()} matching</span>
      </div>
      {group === 'tactical' && <div className="lesson-tactic-filters" role="group" aria-label="Tactical category">
        {tacticalCategories.map(item => <button type="button" key={item.key} aria-pressed={tactical === item.key}
          onClick={() => setTactical(item.key)}>{item.label} <span>({(data.categories.find(category => category.key === item.key)?.counts.total ?? 0).toLocaleString()})</span></button>)}
      </div>}
      <div className="lesson-severity-filters" role="group" aria-label="Error severity">
        {(['all', ...lessonSeverities] as const).map(severity => <button type="button" key={severity}
          aria-pressed={filter === severity} onClick={() => setFilter(severity)}>{severityLabels[severity]}</button>)}
      </div>
      {group === 'positional' && <p className="lesson-explorer-context">Grouped by the piece in Stockfish’s best move.</p>}
      {matching === 0 ? <div className="lesson-no-matches" role="status">
        <p>{filter === 'all' ? `No ${group === 'tactical' ? category?.label.toLowerCase() ?? 'tactical errors' : `${group} errors`} in your saved analysis.`
          : `No ${filter === 'inaccuracy' ? 'inaccuracies' : `${filter}s`} in this category.`}</p>
        {filter !== 'all' && <button type="button" className="text-button" onClick={() => setFilter('all')}>Show all severities</button>}
      </div> : group === 'unclassified' ? <div className="lesson-unclassified-detail">
        <p>These moves do not have a current tactical or positional label.</p>
        <SeverityBreakdown counts={filter === 'all' ? data.unclassified : {
          inaccuracy: 0, mistake: 0, blunder: 0, total: matching, [filter]: matching,
        }}/>
        <a className="back-link" href="#games">Review games to add lesson categories <ArrowRight size={16}/></a>
      </div> : <div className="lesson-topics" key={`${group}:${tactical}:${filter}`}>
        {rows.map(row => <details className="lesson-topic" key={row.key}>
          <summary>
            <span className="lesson-topic-heading"><span>{row.label}</span>
              <span className="lesson-topic-count">{row.matching.toLocaleString()}<ChevronRight size={19} aria-hidden="true"/></span>
            </span>
            <span className="lesson-topic-track" aria-hidden="true"><span style={{width: `${row.matching / matching * 100}%`}}/></span>
            <span className="visually-hidden">{Math.round(row.matching / matching * 100)}% of matching errors. Expand severity breakdown.</span>
          </summary>
          <div className="lesson-topic-detail">
            <p>{row.matching.toLocaleString()} of {matching.toLocaleString()} matching errors · {Math.round(row.matching / matching * 100)}%</p>
            <SeverityBreakdown counts={row.counts}/>
          </div>
        </details>)}
      </div>}
      <div className="lesson-legend" aria-label="Severity colors">{lessonSeverities.map(severity =>
        <span key={severity}><span className={`lesson-severity-dot ${severity}`} aria-hidden="true"/>{severityLabels[severity]}</span>
      )}</div>
    </section>
  </>;
}

export default function Lessons({username, profilesLoading, profileError, onRetryProfiles, multiGameOpen = false}: {
  username: string;
  profilesLoading: boolean; profileError: string; onRetryProfiles: () => void;
  multiGameOpen?: boolean;
}) {
  const [data, setData] = useState<LessonAnalytics | null>(null);
  const [loading, setLoading] = useState(!!username);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!username) { setData(null); setLoading(false); return; }
    const controller = new AbortController();
    setLoading(true); setError('');
    api<LessonAnalytics>(`/api/lessons?username=${encodeURIComponent(username)}`, {signal: controller.signal})
      .then(result => { if (!controller.signal.aborted) { setData(result); setLoading(false); } })
      .catch(err => { if (!controller.signal.aborted) { setError(err instanceof Error ? err.message : 'Could not load your lessons.'); setLoading(false); } });
    return () => controller.abort();
  }, [username, revision]);
  const busy = loading || profilesLoading;
  const failure = profileError || error;

  if (multiGameOpen) return <MultiGameAnalysis username={username}
    summary={data} summaryLoading={busy} summaryError={failure}
    onRefreshSummary={() => profileError ? onRetryProfiles() : setRevision(value => value + 1)}/>;

  return <div className="lessons-page">
    <div className="lessons-heading">
      <div><h1>Lessons</h1><p>Missed tactics, allowed tactics, and positional choices.</p></div>
      <div className="profile-row lessons-controls">
        <a className="secondary-button" href="#lessons/multi-game">Multi-game analysis <ArrowRight size={16}/></a>
        {username && <>
        <button className="icon-button" aria-label="Refresh lessons" title="Refresh lessons" disabled={busy}
          onClick={() => setRevision(value => value + 1)}><RefreshCw size={16}/></button>
        </>}
      </div>
    </div>
    {failure ? <div className="lessons-empty" role="alert"><CircleAlert size={24}/><h2>Could not load lessons</h2><p>{failure}</p>
      <button className="secondary-button" onClick={() => profileError ? onRetryProfiles() : setRevision(value => value + 1)}>Try again</button></div>
      : busy ? <div className="lessons-loading" role="status"><p>Loading your error breakdown…</p>
        <div className="lesson-skeleton" aria-hidden="true"><div/><div/><div/></div></div>
      : !data?.analyzed_moves ? <div className="lessons-empty"><h2>Start with a game analysis</h2>
        <p>Analyze a game from your library to see inaccuracies, mistakes, and blunders here. Saved coach reviews add the tactical and positional categories.</p>
        <a className="back-link" href="#games">Go to your game library <ArrowRight size={16}/></a></div>
      : <>
        <div className="lessons-summary"><p><strong>{data.errors.total.toLocaleString()}</strong> {data.errors.total === 1 ? 'error' : 'errors'} in your analyzed moves</p>
          <span>{lessonCoverage(data)}</span></div>
        {data.errors.total === 0 && <p className="lessons-note">No inaccuracies, mistakes, or blunders in the saved analysis so far.</p>}
        <LessonExplorer data={data}/>
        <div className="lessons-notes">
          {data.outdated_reviews > 0 && <p>{data.outdated_reviews} {data.outdated_reviews === 1 ? 'error needs an updated coach review' : 'errors need updated coach reviews'}. Earlier reviews use different categories.
            {' '}<a href="#games">Update reviews in your game library</a>, or run coach on individual moves.</p>}
          {data.pending_reviews > 0 && <p>{data.pending_reviews} {data.pending_reviews === 1 ? 'error still needs' : 'errors still need'} a coach review to add lesson categories.</p>}
          <p>Each move is counted once per game. Good and uncertain moves are excluded.</p>
        </div>
      </>}
  </div>;
}
