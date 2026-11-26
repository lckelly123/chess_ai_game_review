export const analysisResetEvent = 'chess-study:analysis-reset';
export type AnalysisReset = { game_ids: string[]; games_reset: number; engine_records: number; coach_records: number; reports: number };

export function clearAnalysisStorage(storage: Pick<Storage, 'length' | 'key' | 'removeItem'>, gameIds: string[], all = false) {
  const ids = new Set(gameIds);
  const remove: string[] = [];
  for (let index = 0; index < storage.length; index++) {
    const key = storage.key(index);
    if (!key) continue;
    if (key.startsWith('review-practice:v1:')) {
      if (all) { remove.push(key); continue; }
      try {
        const identity: unknown = JSON.parse(key.slice('review-practice:v1:'.length));
        if (Array.isArray(identity) && ids.has(identity[0])) remove.push(key);
      } catch { /* Unknown storage keys are left alone. */ }
    } else if (key.startsWith('coach-speech:v1:') && (all || ids.has(key.slice('coach-speech:v1:'.length).split(':')[0]))) {
      remove.push(key);
    } else if (key.startsWith('position:') && (all || ids.has(key.slice('position:'.length)))) {
      remove.push(key);
    }
  }
  remove.forEach(key => storage.removeItem(key));
}

export function publishAnalysisReset(result: AnalysisReset, all: boolean) {
  let storageCleared = true;
  try {
    // Also notifies other open tabs; the timestamp makes repeated resets distinct.
    localStorage.setItem(analysisResetEvent, JSON.stringify({...result, at: Date.now()}));
    clearAnalysisStorage(localStorage, result.game_ids, all);
  } catch { storageCleared = false; }
  window.dispatchEvent(new CustomEvent<AnalysisReset>(analysisResetEvent, {detail: result}));
  return storageCleared;
}
