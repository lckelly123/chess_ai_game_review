import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, BookOpen, Check, CircleAlert, Clock3, LoaderCircle, RefreshCw, Search, X } from 'lucide-react';
import { BrandKnight } from './Board';
import Replay from './Replay';
import { api, perspective, readStored, store, timeControl } from './types';
import type { Game, GameDetail, ImportJob, Profile } from './types';

function readReplayRoute() {
  const match = window.location.hash.match(/^#game\/([\w-]+)(?:\?(.*))?$/);
  return match ? { id: match[1], username: new URLSearchParams(match[2]).get('player') || readStored('username') } : null;
}

export default function App() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [username, setUsername] = useState('');
  const [input, setInput] = useState(readStored('username'));
  const [limit, setLimit] = useState(50);
  const [games, setGames] = useState<Game[]>([]);
  const [replayRoute, setReplayRoute] = useState(readReplayRoute);
  const [detail, setDetail] = useState<GameDetail | null>(null);
  const [search, setSearch] = useState('');
  const [speed, setSpeed] = useState('all');
  const [result, setResult] = useState('all');
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [jobId, setJobId] = useState(readStored('importJob'));
  const [job, setJob] = useState<ImportJob | null>(null);
  const [error, setError] = useState('');
  const [libraryError, setLibraryError] = useState('');
  const [detailError, setDetailError] = useState('');
  const [revision, setRevision] = useState(0);
  const [boot, setBoot] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const gameListRef = useRef<HTMLUListElement>(null);
  const libraryPosition = useRef({ page: 0, list: 0, game: '' });
  const wasReplaying = useRef(!!replayRoute);
  const busy = submitting || !!jobId;

  useEffect(() => {
    const navigate = () => setReplayRoute(readReplayRoute());
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);

  useLayoutEffect(() => {
    if (replayRoute) {
      window.scrollTo(0, 0);
      workspaceRef.current?.focus({ preventScroll: true });
    } else if (wasReplaying.current) {
      const list = gameListRef.current;
      if (list) {
        list.scrollTop = libraryPosition.current.list;
        list.querySelector<HTMLAnchorElement>(`[data-game-id="${libraryPosition.current.game}"]`)?.focus({ preventScroll: true });
      }
      window.scrollTo(0, libraryPosition.current.page);
    }
    wasReplaying.current = !!replayRoute;
    document.title = replayRoute ? 'Chess study — Game replay' : 'Chess study — Your game library';
  }, [replayRoute]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setLibraryError('');
    api<Profile[]>('/api/profiles', { signal: controller.signal }).then(data => {
      setProfiles(data);
      const remembered = readStored('username');
      setUsername(data.find(p => p.username === remembered)?.username || data[0]?.username || '');
      if (!data.length) setLoading(false);
    }).catch(err => { if (err.name !== 'AbortError') { setLibraryError('Could not load your library. Check that the app server is running.'); setLoading(false); } });
    return () => controller.abort();
  }, [boot]);

  useEffect(() => {
    if (!username) return;
    const controller = new AbortController();
    setLoading(true); setLibraryError(''); store('username', username);
    api<Game[]>(`/api/games?username=${encodeURIComponent(username)}`, { signal: controller.signal }).then(data => {
      setGames(data);
      setLoading(false);
    }).catch(err => { if (err.name !== 'AbortError') { setLibraryError(err.message); setLoading(false); } });
    return () => controller.abort();
  }, [username, revision, boot]);

  useEffect(() => {
    if (!replayRoute) { setDetail(null); setDetailError(''); setDetailLoading(false); return; }
    const controller = new AbortController();
    setDetailLoading(true); setDetailError(''); setDetail(null);
    api<GameDetail>(`/api/games/${replayRoute.id}`, { signal: controller.signal }).then(data => {
      setDetail(data); setDetailLoading(false);
    }).catch(err => { if (err.name !== 'AbortError') { setDetailError(err.message); setDetailLoading(false); } });
    return () => controller.abort();
  }, [replayRoute, revision]);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer: number;
    const poll = async () => {
      try {
        const current = await api<ImportJob>(`/api/imports/${jobId}`);
        if (cancelled) return;
        setJob(current);
        if (current.status === 'completed' || current.status === 'failed') {
          store('importJob', '');
          if (current.status === 'completed') {
            const updated = await api<Profile[]>('/api/profiles');
            if (cancelled) return;
            setProfiles(updated); setUsername(current.username); setInput(current.username);
            setSearch(''); setSpeed('all'); setResult('all'); setRevision(r => r + 1);
          }
          setJobId('');
        } else timer = window.setTimeout(poll, 800);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Could not check the import. Try again.');
        setJobId(''); store('importJob', '');
      }
    };
    void poll();
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [jobId]);

  async function importGames(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true); setError(''); setJob(null);
    try {
      const created = await api<ImportJob>('/api/imports', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: input.trim(), limit }) });
      setJob(created); store('importJob', created.id); setJobId(created.id);
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not start the import.'); }
    finally { setSubmitting(false); }
  }

  const filtered = games.filter(game => {
    const player = perspective(game, username);
    return `${game.white} ${game.black}`.toLowerCase().includes(search.toLowerCase()) && (speed === 'all' || game.time_class === speed) && (result === 'all' || player.result === result);
  });
  const activeProfile = profiles.find(p => p.username === username);

  return <>
    <header className="site-header"><a className="wordmark" href="#games" aria-label="Chess study home"><span className="brand-piece"><BrandKnight/></span>Chess <span>study</span></a><span className="header-purpose"><BookOpen size={16}/> {replayRoute ? 'Game replay' : 'Your game library'}</span><span className="local-label"><span/> Saved on this device</span></header>
    <main className={`app-layout ${replayRoute ? 'replay-layout' : 'library-layout'}`}>
      {!replayRoute ? <div className="library">
        <div className="library-heading"><h1>Your game library.</h1><p>Import your Chess.com games and choose one to replay.</p></div>
        <section className="import-section" aria-label="Import games from Chess.com">
          <div className="import-fields">
          <form onSubmit={importGames}>
            <div className="username-field"><label htmlFor="username">Chess.com username</label>
            <div className="username-input"><input ref={inputRef} id="username" name="username" autoComplete="off" autoCapitalize="none" spellCheck={false} placeholder="Your username" required maxLength={50} pattern="[A-Za-z0-9_\-]+" title="Use the username from your Chess.com profile." value={input} onChange={e => setInput(e.target.value)} disabled={busy}/>{input && !busy && <button type="button" className="clear-input" aria-label="Clear username" onClick={() => { setInput(''); inputRef.current?.focus(); }}><X size={15}/></button>}</div>
            </div>
            <div className="import-actions"><select aria-label="Number of recent games to import" value={limit} onChange={e => setLimit(Number(e.target.value))} disabled={busy}><option value={20}>Latest 20</option><option value={50}>Latest 50</option><option value={100}>Latest 100</option></select><button type="submit" className="primary-button" disabled={busy || !input.trim()}>{busy ? <><LoaderCircle className="spin" size={16}/> Importing</> : <>Import games <ArrowRight size={16}/></>}</button></div>
          </form>
          <p className="import-hint">Completed games only. Recent games may take time to appear.</p>
          {(job || error) && <div className={`import-status ${(error || job?.status === 'failed') ? 'error' : ''}`} role={error || job?.status === 'failed' ? 'alert' : 'status'}>{error || job?.status === 'failed' ? <CircleAlert size={17}/> : busy ? <LoaderCircle size={17} className="spin"/> : <Check size={17}/>}<div>{error || job?.message}{!!job?.skipped && job.status === 'completed' && <small>{job.skipped} unsupported or unreadable {job.skipped === 1 ? 'game' : 'games'} skipped.</small>}</div></div>}
          </div>
        </section>
        <section className="library-section" aria-labelledby="library-title">
          <div className="section-heading"><h2 id="library-title">Saved games</h2>
          {profiles.length > 0 && <div className="profile-row"><select aria-label="Imported player" value={username} onChange={e => { setGames([]); setUsername(e.target.value); setInput(e.target.value); setSearch(''); setSpeed('all'); setResult('all'); }}><option value="" disabled>Select player</option>{profiles.map(p => <option key={p.username} value={p.username}>{p.username}</option>)}</select><button className="icon-button" title="Refresh saved library" aria-label="Refresh saved library" disabled={loading} onClick={() => setBoot(b => b + 1)}><RefreshCw size={15}/></button></div>}</div>
          {games.length > 0 && <div className="library-toolbar"><div className="search-field"><Search size={16}/><input aria-label="Search opponents" placeholder="Find an opponent…" value={search} onChange={e => setSearch(e.target.value)}/></div><div className="filters"><select aria-label="Filter by time control" value={speed} onChange={e => setSpeed(e.target.value)}><option value="all">All speeds</option><option value="rapid">Rapid</option><option value="blitz">Blitz</option><option value="bullet">Bullet</option><option value="daily">Daily</option></select><select aria-label="Filter by result" value={result} onChange={e => setResult(e.target.value)}><option value="all">All results</option><option value="win">Wins</option><option value="loss">Losses</option><option value="draw">Draws</option></select></div></div>}
          {libraryError ? <div className="library-empty" role="alert"><CircleAlert size={22}/><p>{libraryError}</p><button className="text-button" onClick={() => setBoot(b => b + 1)}>Try again</button></div> : loading ? <div className="library-empty" role="status"><LoaderCircle className="spin" size={24}/><p>Loading your games…</p></div> : !games.length ? <div className="library-empty"><BookOpen size={26}/><h3>{profiles.length ? 'No games imported yet' : 'A home for your games'}</h3><p>Import your recent games to keep them here, ready to revisit.</p></div> : <>
            <div className="list-summary"><span aria-live="polite">{filtered.length} {filtered.length === 1 ? 'game' : 'games'}</span><span>Newest first</span></div>
            {!!filtered.length && <div className="game-list-heading" aria-hidden="true"><span>Result</span><span>Opponent</span><span>Time control</span><span>Played</span><span/></div>}
            <ul className="game-list" ref={gameListRef} aria-label="Saved games">{filtered.map(game => {
              const player = perspective(game, username);
              return <li className="game-item" key={game.id}>
                <span className={`result-mark ${player.result}`}>{player.result === 'win' ? 'Win' : player.result === 'loss' ? 'Loss' : 'Draw'}</span>
                <span className="game-item-info"><span className="opponent">{player.opponent}<span>{player.opponentRating ?? 'Unrated'}</span></span><span className="game-item-meta"><span className={`tiny-token ${player.isWhite ? 'white' : 'black'}`} aria-hidden="true"/>You played {player.isWhite ? 'White' : 'Black'}</span></span>
                <span className="game-speed"><span className="capitalize">{game.time_class}</span><span>{timeControl(game.time_control)}</span></span>
                <time className="game-date" dateTime={new Date(game.end_time * 1000).toISOString()}>{new Date(game.end_time * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</time>
                <a className="analyze-button" data-game-id={game.id} href={`#game/${game.id}?player=${encodeURIComponent(username)}`} aria-label={`Analyze game against ${player.opponent}, ${new Date(game.end_time * 1000).toLocaleDateString()}`} onClick={() => { libraryPosition.current = { page: window.scrollY, list: gameListRef.current?.scrollTop || 0, game: game.id }; }}>Analyze <ArrowRight size={15}/></a>
              </li>;
            })}</ul>
            {!filtered.length && <div className="library-empty"><p>No games match these filters.</p><button className="text-button" onClick={() => { setSearch(''); setSpeed('all'); setResult('all'); }}>Clear filters</button></div>}
          </>}
          {activeProfile && <p className="last-sync"><Clock3 size={13}/> Last import {new Date(activeProfile.last_synced * 1000).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</p>}
        </section>
        <footer className="library-footer">Independent project. Not affiliated with Chess.com.</footer>
      </div> : <div className="workspace" ref={workspaceRef} tabIndex={-1} aria-label="Game replay workspace">
        <nav className="replay-navigation" aria-label="Game navigation"><a className="back-link" href="#games"><ArrowLeft size={17}/> Back to games</a><span>Replay & explore</span></nav>
        {detailError ? <div className="workspace-loading" role="alert"><CircleAlert size={28}/><h1>Could not open this game</h1><p>{detailError}</p><button className="secondary-button" onClick={() => setRevision(r => r + 1)}>Try again</button></div> : detailLoading || !detail || detail.id !== replayRoute.id ? <div className="workspace-loading" role="status"><LoaderCircle className="spin" size={28}/><p>Setting up the board…</p></div> : <Replay key={`${detail.id}:${replayRoute.username}`} game={detail} username={replayRoute.username}/>}
      </div>}
    </main>
  </>;
}
