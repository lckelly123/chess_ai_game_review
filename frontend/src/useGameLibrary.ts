import { useEffect, useState } from 'react';
import { api, readStored, store } from './types';
import type { Game, ImportJob, Profile } from './types';
import { refreshAnalytics } from './analyticsData';

type SyncState = { status: 'idle' | 'checking' | 'completed' | 'failed'; message: string; added: number; skipped: number };
const idleSync: SyncState = { status: 'idle', message: '', added: 0, skipped: 0 };

export default function useGameLibrary() {
  const [username, setUsername] = useState(() => readStored('username').trim().toLowerCase());
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(true);
  const [profilesReady, setProfilesReady] = useState(false);
  const [profileError, setProfileError] = useState('');
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(!!username);
  const [libraryError, setLibraryError] = useState('');
  const [sync, setSync] = useState<SyncState>(idleSync);
  const [boot, setBoot] = useState(0);
  const [revision, setRevision] = useState(0);
  const [syncAttempt, setSyncAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setProfilesLoading(true); setProfileError('');
    api<Profile[]>('/api/profiles', {signal: controller.signal}).then(data => {
      if (controller.signal.aborted) return;
      setProfiles(data);
      setUsername(current => current || data[0]?.username || '');
      setProfilesReady(true);
    }).catch(err => {
      if (!controller.signal.aborted) setProfileError(err instanceof Error ? err.message : 'Could not load your account.');
    }).finally(() => { if (!controller.signal.aborted) setProfilesLoading(false); });
    return () => controller.abort();
  }, [boot]);

  useEffect(() => {
    if (!username) { setLoading(false); return; }
    const controller = new AbortController();
    store('username', username);
    setLoading(true); setLibraryError('');
    api<Game[]>(`/api/games?username=${encodeURIComponent(username)}`, {signal: controller.signal}).then(data => {
      if (!controller.signal.aborted) setGames(data);
    }).catch(err => {
      if (!controller.signal.aborted) setLibraryError(err instanceof Error ? err.message : 'Could not load your games.');
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [username, revision, boot]);

  useEffect(() => {
    if (!username || !profilesReady) return;
    const controller = new AbortController();
    let timer: number | undefined;
    setSync({ ...idleSync, status: 'checking' });
    // Refresh saved statistics even if the independent Chess.com sync fails.
    // Analytics reports its own errors when opened; syncing never waits on it.
    void refreshAnalytics(username).catch(() => undefined);

    const fail = (err: unknown) => {
      if (!controller.signal.aborted) setSync({...idleSync, status: 'failed',
        message: err instanceof Error ? err.message : 'Could not check for new games. Please try again.'});
    };
    const receive = async (job: ImportJob) => {
      if (controller.signal.aborted) return;
      if (job.status === 'failed') { fail(new Error(job.message)); return; }
      if (job.status === 'completed') {
        void refreshAnalytics(username).catch(() => undefined);
        // Refresh the list without replacing it with a loading screen or
        // changing filters, scroll position, or the user's current account.
        setRevision(value => value + 1);
        const updated = await api<Profile[]>('/api/profiles', {signal: controller.signal});
        if (controller.signal.aborted) return;
        setProfiles(updated);
        setSync({status: 'completed', message: job.message, added: job.added, skipped: job.skipped});
        return;
      }
      timer = window.setTimeout(() => {
        void api<ImportJob>(`/api/imports/${job.id}`, {signal: controller.signal}).then(receive).catch(fail);
      }, 800);
    };

    // The server joins an already running job for this username. This resumes
    // on reload, survives stale browser job IDs, and coalesces StrictMode starts.
    void api<ImportJob>('/api/imports', {method: 'POST', signal: controller.signal,
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username, sync: true})})
      .then(receive).catch(fail);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [username, profilesReady, syncAttempt]);

  function selectAccount(value: string) {
    const next = value.trim().toLowerCase();
    if (next === username) return;
    store('username', next);
    setGames([]); setLibraryError(''); setLoading(true); setSync(idleSync); setUsername(next);
  }

  return { username, profiles, profilesLoading, profileError, games, setGames, loading,
    libraryError, sync, selectAccount,
    retrySync: () => setSyncAttempt(value => value + 1),
    reloadLibrary: () => setBoot(value => value + 1) };
}
