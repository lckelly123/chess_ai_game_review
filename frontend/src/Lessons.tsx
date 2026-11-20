import { useEffect, useState } from 'react';
import { ArrowRight, CircleAlert, RefreshCw } from 'lucide-react';
import { api } from './types';
import type { Profile } from './types';
import { lessonCoverage } from './lessonsData';
import type { ErrorCounts, LessonAnalytics } from './lessonsData';
import './lessons.css';

function Counts({counts}: {counts: ErrorCounts}) {
  return <>{(['inaccuracy', 'mistake', 'blunder', 'total'] as const).map(severity =>
    <td key={severity} className={`lesson-count ${severity}${counts[severity] === 0 ? ' zero' : ''}`}>
      {counts[severity].toLocaleString()}
    </td>)}</>;
}

export default function Lessons({profiles, username, onSelectPlayer, profilesLoading, profileError, onRetryProfiles}: {
  profiles: Profile[]; username: string; onSelectPlayer: (username: string) => void;
  profilesLoading: boolean; profileError: string; onRetryProfiles: () => void;
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

  return <div className="lessons-page">
    <div className="lessons-heading">
      <div><h1>Lessons</h1><p>Missed tactics, allowed tactics, and positional choices.</p></div>
      {profiles.length > 0 && <div className="profile-row lessons-controls">
        <label className="visually-hidden" htmlFor="lessons-player">Player for lesson analytics</label>
        <select id="lessons-player" value={username} onChange={event => onSelectPlayer(event.target.value)}>
          {profiles.map(profile => <option key={profile.username} value={profile.username}>{profile.username}</option>)}
        </select>
        <button className="icon-button" aria-label="Refresh lessons" title="Refresh lessons" disabled={busy}
          onClick={() => setRevision(value => value + 1)}><RefreshCw size={16}/></button>
      </div>}
    </div>
    {failure ? <div className="lessons-empty" role="alert"><CircleAlert size={24}/><h2>Could not load lessons</h2><p>{failure}</p>
      <button className="secondary-button" onClick={() => profileError ? onRetryProfiles() : setRevision(value => value + 1)}>Try again</button></div>
      : busy ? <div className="lessons-loading" role="status"><p>Loading your error breakdown…</p>
        <div className="lesson-skeleton" aria-hidden="true">{[0, 1, 2, 3, 4].map(row => <div key={row}/>)}</div></div>
      : !data?.analyzed_moves ? <div className="lessons-empty"><h2>Start with a game analysis</h2>
        <p>Analyze a game from your library to see inaccuracies, mistakes, and blunders here. Saved coach reviews add the tactical and positional categories.</p>
        <a className="back-link" href="#games">Go to your game library <ArrowRight size={16}/></a></div>
      : <>
        <div className="lessons-summary"><p><strong>{data.errors.total.toLocaleString()}</strong> {data.errors.total === 1 ? 'error' : 'errors'} in your analyzed moves</p>
          <span>{lessonCoverage(data)}</span></div>
        {data.errors.total === 0 && <p className="lessons-note">No inaccuracies, mistakes, or blunders in the saved analysis so far.</p>}
          {data.outdated_reviews > 0 && <p className="lessons-note lessons-update">{data.outdated_reviews} {data.outdated_reviews === 1 ? 'error needs an updated coach review' : 'errors need updated coach reviews'}. Earlier reviews use different categories.
            {' '}<a href="#games">Update reviews in your game library</a>, or run coach on individual moves.</p>}
        <div className="lesson-table-wrap">
          <table className="lesson-table">
            <caption className="visually-hidden">Inaccuracies, mistakes, and blunders by tactical and positional subcategory for {username}</caption>
            <colgroup><col className="lesson-name-column"/><col/><col/><col/><col/></colgroup>
            <thead><tr><th scope="col">Subcategory</th>
              <th scope="col" className="inaccuracy"><span className="severity-full">Inaccuracy</span><abbr className="severity-short" title="Inaccuracy">Inacc.</abbr></th>
              <th scope="col" className="mistake">Mistake</th><th scope="col" className="blunder">Blunder</th><th scope="col">Total</th></tr></thead>
            {data.categories.map(category => <tbody key={category.key}>
              <tr className="lesson-group"><th scope="rowgroup">{category.label}</th><Counts counts={category.counts}/></tr>
              {category.subcategories.map(row => <tr className="lesson-detail" key={row.key}>
                <th scope="row">{row.label}</th><Counts counts={row.counts}/></tr>)}
            </tbody>)}
            {data.unclassified.total > 0 && <tbody><tr className="lesson-unclassified"><th scope="row">Unclassified</th><Counts counts={data.unclassified}/></tr></tbody>}
            <tfoot><tr><th scope="row">All errors</th><Counts counts={data.errors}/></tr></tfoot>
          </table>
        </div>
        <div className="lessons-notes">
          <p>Positional rows identify the piece moved by Stockfish’s best move, not the piece you played.</p>
          <p>Each move is counted once per game. Good and uncertain moves are excluded.</p>
          {data.unclassified.total > 0 && <p>{data.unclassified.total} {data.unclassified.total === 1 ? 'error has' : 'errors have'} no current tactical or positional label.
            {data.pending_reviews > 0 && <> {data.pending_reviews} {data.pending_reviews === 1 ? 'still needs' : 'still need'} a coach review.</>}</p>}

        </div>
      </>}
  </div>;
}
