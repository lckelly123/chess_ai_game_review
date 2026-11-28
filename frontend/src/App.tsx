import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, BookOpen, Check, ChevronDown, CircleAlert, Clock3, Code2, ChartNoAxesColumn, LoaderCircle, Search, UserRound } from 'lucide-react';
import { BrandKnight } from './Board';
import Replay from './Replay';
import GameAnalysisAction from './GameAnalysisAction';
import Analytics from './Analytics';
import { api, perspective, readStored, timeControl } from './types';
import type { GameDetail } from './types';
import AccountDialog from './AccountDialog';
import useGameLibrary from './useGameLibrary';
import Dev from './Dev';
import { analysisResetEvent } from './analysisReset';
import type { AnalysisReset } from './analysisReset';
import { resetCoachSpeech } from './useCoachSpeech';

function readReplayRoute() {
  const match = window.location.hash.match(/^#game\/([\w-]+)(?:\?(.*))?$/);
  return match ? { id: match[1], username: new URLSearchParams(match[2]).get('player') || readStored('username') } : null;
}

export default function App() {
  const {username, profiles, profilesLoading, profileError, games, setGames, loading, libraryError,
    sync, selectAccount, reloadLibrary} = useGameLibrary();
  const [accountOpen, setAccountOpen] = useState(false);
  const [replayRoute, setReplayRoute] = useState(readReplayRoute);
  const [analyticsOpen, setAnalyticsOpen] = useState(() => ['#analytics', '#lessons', '#lessons/multi-game'].includes(window.location.hash));
  const [devOpen, setDevOpen] = useState(() => window.location.hash === '#dev');
  const [detail, setDetail] = useState<GameDetail | null>(null);
  const [search, setSearch] = useState('');
  const [speed, setSpeed] = useState('all');
  const [result, setResult] = useState('all');
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [revision, setRevision] = useState(0);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const gameListRef = useRef<HTMLUListElement>(null);
  const libraryPosition = useRef({ page: 0, list: 0, game: '' });
  const wasOutsideLibrary = useRef(!!replayRoute || analyticsOpen || devOpen);
  const reloadLibraryRef = useRef(reloadLibrary);
  reloadLibraryRef.current = reloadLibrary;

  useEffect(() => {
    const reset = (result: AnalysisReset) => {
      const ids = new Set(result.game_ids);
      resetCoachSpeech(result.game_ids);
      setDetail(null);
      setRevision(value => value + 1);
      setGames(current => current.map(game => ids.has(game.id) ? {...game, analysis: null} : game));
      reloadLibraryRef.current();
    };
    const fromWindow = (event: Event) => reset((event as CustomEvent<AnalysisReset>).detail);
    const fromStorage = (event: StorageEvent) => {
      if (event.key !== analysisResetEvent || !event.newValue) return;
      try {
        const result = JSON.parse(event.newValue) as AnalysisReset;
        if (Array.isArray(result.game_ids)) reset(result);
      } catch { /* Ignore incomplete storage notifications. */ }
    };
    window.addEventListener(analysisResetEvent, fromWindow);
    window.addEventListener('storage', fromStorage);
    return () => { window.removeEventListener(analysisResetEvent, fromWindow); window.removeEventListener('storage', fromStorage); };
  }, [setGames]);

  useEffect(() => {
    const navigate = () => {
      if (['#lessons', '#lessons/multi-game'].includes(window.location.hash)) window.history.replaceState(null, '', '#analytics');
      setReplayRoute(readReplayRoute()); setAnalyticsOpen(window.location.hash === '#analytics');
      setDevOpen(window.location.hash === '#dev');
    };
    navigate();
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);

  useLayoutEffect(() => {
    if (replayRoute || analyticsOpen || devOpen) {
      window.scrollTo(0, 0);
      if (replayRoute) workspaceRef.current?.focus({ preventScroll: true });
    } else if (wasOutsideLibrary.current) {
      const list = gameListRef.current;
      if (list) {
        list.scrollTop = libraryPosition.current.list;
        list.querySelector<HTMLAnchorElement>(`[data-game-id="${libraryPosition.current.game}"]`)?.focus({ preventScroll: true });
      }
      window.scrollTo(0, libraryPosition.current.page);
    }
    wasOutsideLibrary.current = !!replayRoute || analyticsOpen || devOpen;
    document.title = devOpen ? 'Chess study — Dev' : analyticsOpen ? 'Chess study — Analytics' : replayRoute ? 'Chess study — Game replay' : 'Chess study — Your game library';
  }, [replayRoute, analyticsOpen, devOpen]);

  useEffect(() => {
    if (!replayRoute) { setDetail(null); setDetailError(''); setDetailLoading(false); return; }
    const controller = new AbortController();
    setDetailLoading(true); setDetailError(''); setDetail(null);
    api<GameDetail>(`/api/games/${replayRoute.id}`, { signal: controller.signal }).then(data => {
      if (controller.signal.aborted) return;
      setDetail(data); setDetailLoading(false);
    }).catch(err => { if (err.name !== 'AbortError') { setDetailError(err.message); setDetailLoading(false); } });
    return () => controller.abort();
  }, [replayRoute, revision]);

  function saveAccount(value: string) {
    if (value === username) return;
    selectAccount(value);
    setSearch(''); setSpeed('all'); setResult('all');
    if (replayRoute) window.location.hash = '#games';
  }

  const filtered = games.filter(game => {
    const player = perspective(game, username);
    return `${game.white} ${game.black}`.toLowerCase().includes(search.toLowerCase()) && (speed === 'all' || game.time_class === speed) && (result === 'all' || player.result === result);
  });
  const activeProfile = profiles.find(p => p.username === username);

  return <>
    <header className="site-header"><a className="wordmark" href="#games" aria-label="Chess study home"><span className="brand-piece"><BrandKnight/></span>Chess <span>study</span></a>
      <nav className="primary-nav" aria-label="Main navigation">
        <a href="#games" aria-current={!analyticsOpen && !devOpen ? 'page' : undefined}><BookOpen size={16}/> <span>Your game library</span></a>
        <a href="#analytics" aria-current={analyticsOpen ? 'page' : undefined} onClick={() => {
          if (!replayRoute && !analyticsOpen && !devOpen) libraryPosition.current = {...libraryPosition.current, page: window.scrollY, list: gameListRef.current?.scrollTop || 0};
        }}><ChartNoAxesColumn size={17}/> Analytics</a>
      </nav>
      <div className="header-tools"><a className="dev-tab" href="#dev" aria-current={devOpen ? 'page' : undefined} onClick={() => {
        if (!replayRoute && !analyticsOpen && !devOpen) libraryPosition.current = {...libraryPosition.current, page: window.scrollY, list: gameListRef.current?.scrollTop || 0};
      }}><Code2 size={16}/>Dev</a><button className="account-button" onClick={() => setAccountOpen(true)} aria-label={username ? `Account settings for ${username}` : 'Add your Chess.com account'}
        aria-haspopup="dialog" aria-expanded={accountOpen}><UserRound size={17}/><span>{username || 'Account'}</span><ChevronDown size={14}/></button></div>
    </header>
    {accountOpen && <AccountDialog username={username} profiles={profiles} onSave={saveAccount} onClose={() => setAccountOpen(false)}/>}
    <main className={`app-layout ${replayRoute ? 'replay-layout' : 'library-layout'}`}>
      {devOpen ? <Dev/> : analyticsOpen ? <Analytics key={`${username}:${revision}`} username={username} profilesLoading={profilesLoading}
        profileError={profileError} onRetryProfiles={reloadLibrary}/>
      : !replayRoute ? <div className="library">
        <div className="library-heading"><div><h1>Your game library</h1><p>Your games, ready for a closer look.</p></div>
          {username && sync.status !== 'failed' && <div className="sync-status" role="status" aria-live="polite" aria-atomic="true">
            {sync.status === 'checking' ? <><LoaderCircle className="spin" size={14}/><span>Checking for new games…</span></>
              : sync.status === 'completed' ? <><Check size={14}/><span>{sync.added ? `${sync.added} new ${sync.added === 1 ? 'game' : 'games'} added` : 'Checked just now'}</span></>
              : activeProfile ? <><Clock3 size={14}/><span>Last checked {new Date(activeProfile.last_synced * 1000).toLocaleString(undefined, {month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'})}</span></> : null}
          </div>}
        </div>
        {sync.status === 'completed' && sync.skipped > 0 && <p className="sync-footnote">{sync.skipped} unsupported or unreadable {sync.skipped === 1 ? 'game was' : 'games were'} skipped.</p>}
        <section className="library-section" aria-label="Saved games">
          {games.length > 0 && <div className="library-toolbar"><div className="search-field"><Search size={16}/><input aria-label="Search opponents" placeholder="Find an opponent…" value={search} onChange={e => setSearch(e.target.value)}/></div><div className="filters"><select aria-label="Filter by time control" value={speed} onChange={e => setSpeed(e.target.value)}><option value="all">All speeds</option><option value="rapid">Rapid</option><option value="blitz">Blitz</option><option value="bullet">Bullet</option><option value="daily">Daily</option></select><select aria-label="Filter by result" value={result} onChange={e => setResult(e.target.value)}><option value="all">All results</option><option value="win">Wins</option><option value="loss">Losses</option><option value="draw">Draws</option></select></div></div>}
          {(libraryError || profileError) && <div className="sync-notice" role="alert"><CircleAlert size={18}/><div><p>{libraryError || profileError}</p>
            <button className="text-button" onClick={reloadLibrary}>Try again</button></div></div>}
          {!games.length && (loading || profilesLoading) ? <div className="library-empty" role="status"><LoaderCircle className="spin" size={24}/><p>Loading your games…</p></div>
            : !games.length && !username ? <div className="library-empty account-empty"><BookOpen size={30}/><h2>A home for your games</h2>
              <p>Add your Chess.com account to see your games.<br/>We’ll keep your library up to date automatically.</p>
              <button className="primary-button" onClick={() => setAccountOpen(true)}>Add Chess.com account <ArrowRight size={16}/></button></div>
            : !games.length ? <div className="library-empty" role="status">{sync.status === 'checking' ? <><LoaderCircle className="spin" size={24}/><h3>Finding your recent games</h3><p>Your completed games will appear here.</p></>
              : <><BookOpen size={26}/><h3>{sync.status === 'failed' || libraryError || profileError ? 'Your library will appear here' : 'No completed games yet'}</h3>
                <p>{libraryError || profileError ? 'Try again or check your account settings above.' : 'We’ll check for completed standard-chess games each time you visit. Recent games may take time to appear.'}</p></>}</div> : <>
            <div className="list-summary"><span aria-live="polite">{filtered.length} {filtered.length === 1 ? 'game' : 'games'}</span><span>Newest first</span></div>
            {!!filtered.length && <div className="game-list-heading" aria-hidden="true"><span>Result</span><span>Opponent</span><span>Time control</span><span>Played</span><span/></div>}
            <ul className="game-list" ref={gameListRef} aria-label="Saved games">{filtered.map(game => {
              const player = perspective(game, username);
              return <li className="game-item" key={game.id}>
                <span className={`result-mark ${player.result}`}>{player.result === 'win' ? 'Win' : player.result === 'loss' ? 'Loss' : 'Draw'}</span>
                <span className="game-item-info"><span className="opponent">{player.opponent}<span>{player.opponentRating ?? 'Unrated'}</span></span><span className="game-item-meta"><span className={`tiny-token ${player.isWhite ? 'white' : 'black'}`} aria-hidden="true"/>You played {player.isWhite ? 'White' : 'Black'}</span></span>
                <span className="game-speed"><span className="capitalize">{game.time_class}</span><span>{timeControl(game.time_control)}</span></span>
                <time className="game-date" dateTime={new Date(game.end_time * 1000).toISOString()}>{new Date(game.end_time * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</time>
                <GameAnalysisAction key={`${game.id}:${username}:${revision}`} game={game} username={username}
                  onUpdate={analysis => setGames(current => current.map(item => item.id === game.id ? {...item, analysis} : item))}
                  onOpen={() => { libraryPosition.current = { page: window.scrollY, list: gameListRef.current?.scrollTop || 0, game: game.id }; }}/>
              </li>;
            })}</ul>
            {!filtered.length && <div className="library-empty"><p>No games match these filters.</p><button className="text-button" onClick={() => { setSearch(''); setSpeed('all'); setResult('all'); }}>Clear filters</button></div>}
          </>}
        </section>
        <footer className="library-footer">Independent project. Not affiliated with Chess.com.</footer>
      </div> : <div className="workspace" ref={workspaceRef} tabIndex={-1} aria-label="Game replay workspace">
        <nav className="replay-navigation" aria-label="Game navigation"><a className="back-link" href="#games"><ArrowLeft size={17}/> Back to games</a></nav>
        {detailError ? <div className="workspace-loading" role="alert"><CircleAlert size={28}/><h1>Could not open this game</h1><p>{detailError}</p><button className="secondary-button" onClick={() => setRevision(r => r + 1)}>Try again</button></div> : detailLoading || !detail || detail.id !== replayRoute.id ? <div className="workspace-loading" role="status"><LoaderCircle className="spin" size={28}/><p>Setting up the board…</p></div> : <Replay key={`${detail.id}:${replayRoute.username}`} game={detail} username={replayRoute.username}/>}
      </div>}
    </main>
  </>;
}
