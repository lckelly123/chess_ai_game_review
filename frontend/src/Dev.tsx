import { useEffect, useRef, useState } from 'react';
import { Check, CircleAlert, LoaderCircle, RefreshCw, Search } from 'lucide-react';
import { api, timeControl } from './types';
import type { Game } from './types';
import { publishAnalysisReset } from './analysisReset';
import type { AnalysisReset } from './analysisReset';
import './dev.css';

function ResetConfirmation({game, count, onClose, onConfirm}: {
  game: Game | 'all'; count: number; onClose: () => void; onConfirm: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const element = dialog.current!;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element.showModal(); cancel.current?.focus();
    return () => { element.close(); opener?.focus(); };
  }, []);
  return <dialog ref={dialog} className="account-dialog reset-dialog" aria-labelledby="reset-title" aria-describedby="reset-description" onCancel={onClose}>
    <h2 id="reset-title">{game === 'all' ? `Clear analysis for all ${count} ${count === 1 ? 'game' : 'games'}?` : 'Clear this game’s analysis?'}</h2>
    {game !== 'all' && <p className="reset-game-name">{game.white} vs {game.black}</p>}
    <p id="reset-description">This removes engine results, coach reviews, practice attempts and related multi-game reports. Running analysis will stop. This cannot be undone.</p>
    <p>The original {game === 'all' ? 'games and their moves stay' : 'game and its moves stay'} in your library.</p>
    <div className="reset-dialog-actions"><button ref={cancel} className="secondary-button" onClick={onClose}>Cancel</button>
      <button className="danger-button" onClick={onConfirm}>{game === 'all' ? 'Clear all analysis' : 'Clear analysis'}</button></div>
  </dialog>;
}

export default function Dev() {
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [revision, setRevision] = useState(0);
  const [search, setSearch] = useState('');
  const [confirmation, setConfirmation] = useState<Game | 'all' | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setLoadError('');
    api<Game[]>('/api/dev/games', {signal: controller.signal}).then(data => {
      if (!controller.signal.aborted) setGames(data);
    }).catch(err => { if (!controller.signal.aborted) setLoadError(err.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [revision]);

  async function clear(target: Game | 'all') {
    setConfirmation(null); setPending(target === 'all' ? 'all' : target.id); setError(''); setMessage('');
    try {
      const result = await api<AnalysisReset>('/api/dev/analysis/reset', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(target === 'all' ? {} : {game_id: target.id})});
      const localCleared = publishAnalysisReset(result, target === 'all');
      const label = target === 'all' ? `${result.games_reset} ${result.games_reset === 1 ? 'game' : 'games'}` : `${target.white} vs ${target.black}`;
      setMessage(`Analysis cleared for ${label}. Ready for a fresh run.${localCleared ? '' : ' Browser storage is unavailable; old attempts will be ignored on reload.'}`);
      setRevision(value => value + 1);
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not clear analysis. Try again.'); }
    finally { setPending(null); }
  }

  const filtered = games.filter(game => `${game.white} ${game.black} ${new Date(game.end_time * 1000).toLocaleDateString()}`.toLowerCase().includes(search.trim().toLowerCase()));
  return <section className="dev-screen" aria-labelledby="dev-title">
    <div className="library-heading"><div><h1 id="dev-title" ref={heading} tabIndex={-1}>Reset analysis</h1>
      <p>Start fresh with any saved game. Original games and moves are kept.</p></div>
      <button className="secondary-button" onClick={() => setRevision(value => value + 1)} disabled={loading || pending !== null}><RefreshCw size={15}/> Refresh</button></div>
    <section className="dev-clear-all" aria-labelledby="clear-all-title"><div><h2 id="clear-all-title">Clear all analysis</h2>
      <p>Reset engine results, coach reviews and practice attempts for every game across all saved accounts. Related multi-game reports are cleared too.</p></div>
      <button className="danger-button" disabled={!games.length || loading || !!loadError || pending !== null} onClick={() => setConfirmation('all')}>
        {pending === 'all' && <LoaderCircle size={15} className="spin"/>}Clear all{games.length > 0 ? ` (${games.length})` : ''}</button></section>
    <div className="dev-feedback" aria-live="polite" aria-atomic="true">
      {pending !== null ? <p role="status"><LoaderCircle size={16} className="spin"/> Stopping running analysis and clearing saved results…</p>
        : message ? <p role="status"><Check size={16}/>{message}</p> : null}
      {error && <p className="analysis-error" role="alert"><CircleAlert size={16}/>{error}</p>}
    </div>
    <div className="dev-list-heading"><h2>Clear one game</h2><span>All saved accounts</span></div>
    <div className="search-field"><Search size={16}/><input aria-label="Search games to reset" placeholder="Search players or date…" value={search} onChange={event => setSearch(event.target.value)}/></div>
    {loadError ? <div className="library-empty" role="alert"><p>{loadError}</p><button className="text-button" onClick={() => setRevision(value => value + 1)}>Try again</button></div>
      : loading && !games.length ? <div className="library-empty" role="status"><LoaderCircle className="spin" size={24}/><p>Loading saved games…</p></div>
      : !games.length ? <div className="library-empty"><h3>No saved games yet</h3><p>Add a player account to bring games into your library.</p></div>
      : <><div className="list-summary"><span>{filtered.length} {filtered.length === 1 ? 'game' : 'games'}</span><span>Newest first</span></div>
        <ul className="dev-game-list" aria-label="Games available to reset">{filtered.map(game => <li key={game.id}>
          <div className="dev-game-info"><h3>{game.white} <span>vs</span> {game.black}</h3><p><span className="capitalize">{game.time_class}</span> · {timeControl(game.time_control)} · {game.result}</p></div>
          <time dateTime={new Date(game.end_time * 1000).toISOString()}>{new Date(game.end_time * 1000).toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: 'numeric'})}</time>
          <button className="secondary-button" disabled={pending !== null || loading} onClick={() => setConfirmation(game)} aria-label={`Clear analysis for ${game.white} vs ${game.black}`}>
            {pending === game.id && <LoaderCircle size={15} className="spin"/>}Clear analysis</button>
        </li>)}</ul>
        {!filtered.length && <div className="library-empty"><p>No games match your search.</p><button className="text-button" onClick={() => setSearch('')}>Clear search</button></div>}</>}
    {confirmation && <ResetConfirmation game={confirmation} count={games.length} onClose={() => setConfirmation(null)} onConfirm={() => void clear(confirmation)}/>}
  </section>;
}
