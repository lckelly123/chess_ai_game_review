import { useEffect, useRef, useState } from 'react';
import { api, readStored, store } from './types';
import { practiceComplete, practiceKey, restoreAttempts, resultMatches } from './reviewPractice';
import type { PracticeAttempt, PracticeContext, PracticeMove, PracticeResult } from './reviewPractice';
import { analysisResetEvent } from './analysisReset';

type Preview = {key: string; move: PracticeMove; phase: 'checking' | 'retry' | 'accepted' | 'reverting' | 'replaying'};

export function useReviewPractice(gameId: string, color: string, ply: number, fen: string, original: string, eligible: boolean, transitioning: boolean, reducedMotion = false, analysisRevision = 0) {
  const key = practiceKey(gameId, color, ply, fen, original, analysisRevision);
  const [sessions, setSessions] = useState<Record<string, PracticeAttempt[]>>({});
  const attempts = sessions[key] ?? restoreAttempts(readStored(key));
  const complete = practiceComplete(attempts);
  const active = eligible && !complete;
  const [context, setContext] = useState<{key: string; data: PracticeContext} | null>(null);
  const [error, setError] = useState<{key: string; message: string} | null>(null);
  const [revision, setRevision] = useState(0);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const endpoint = `/api/games/${encodeURIComponent(gameId)}/practice/${ply}`;

  useEffect(() => {
    setPreview(null);
    setRevealedKey(null);
    setPendingKey(null);
    return () => { request.current?.abort(); request.current = null; };
  }, [key]);

  const currentPreview = preview?.key === key ? preview : null;
  useEffect(() => {
    if (!currentPreview || currentPreview.phase === 'checking') return;
    const {phase} = currentPreview;
    const delay = phase === 'retry' ? 650 : phase === 'accepted' ? reducedMotion ? 300 : 750 : reducedMotion ? 200 : 420;
    const timer = window.setTimeout(() => {
      setPreview(current => current !== currentPreview ? current
        : phase === 'accepted' ? {...current, phase: 'reverting'}
          : phase === 'reverting' ? {...current, phase: 'replaying'} : null);
      if (phase === 'replaying') setRevealedKey(key);
    }, delay);
    return () => window.clearTimeout(timer);
  }, [currentPreview, key, reducedMotion]);

  useEffect(() => {
    if (!active || transitioning) return;
    const controller = new AbortController();
    setError(null);
    api<PracticeContext>(endpoint, {signal: controller.signal}).then(data => {
      if (controller.signal.aborted) return;
      if (data.fen !== fen || data.original_move !== original) throw new Error('This position has changed. Reload the game to continue.');
      setContext({key, data});
    }).catch(err => {
      if (!controller.signal.aborted) setError({key, message: err instanceof Error ? err.message : 'Could not load legal moves. Try again.'});
    });
    return () => controller.abort();
  }, [active, transitioning, endpoint, key, fen, original, revision]);

  const legalMoves = context?.key === key ? context.data.legal_moves : [];
  const phase = currentPreview?.phase;
  const shownMove = currentPreview && phase !== 'reverting' && phase !== 'replaying' ? currentPreview.move : undefined;
  const busy = pendingKey === key || !!currentPreview;

  async function attemptMove(uci: string) {
    if (!active || transitioning || busy || request.current) return;
    const move = legalMoves.find(item => item.uci === uci);
    if (!move) return;
    const controller = new AbortController();
    request.current = controller;
    setPendingKey(key); setPreview({key, move, phase: 'checking'}); setError(null);
    const entry: PracticeAttempt = {uci, san: move.san, at: new Date().toISOString(), quality: null, lossPp: null, status: 'checking'};
    const updated = [...attempts, entry];
    const resetToken = readStored(analysisResetEvent);
    const save = (values: PracticeAttempt[]) => {
      if (controller.signal.aborted || readStored(analysisResetEvent) !== resetToken) return;
      store(key, JSON.stringify(values));
      setSessions(current => ({...current, [key]: values}));
    };
    save(updated);
    let accepted = false;
    try {
      const result = await api<PracticeResult>(endpoint, {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({fen, original_move: original, move: uci}), signal: controller.signal});
      if (controller.signal.aborted) return;
      if (!resultMatches(result, fen, original, uci)) throw new Error('The move result did not match this position. Try again.');
      accepted = result.accepted;
      save([...attempts, {...entry, status: 'graded', quality: result.quality.status, lossPp: result.quality.winning_chances_loss_pp}]);
    } catch (err) {
      if (controller.signal.aborted) return;
      save([...attempts, {...entry, status: 'error'}]);
      setError({key, message: err instanceof Error ? err.message : 'Could not check this move. Try again.'});
    } finally {
      if (!controller.signal.aborted) {
        request.current = null; setPendingKey(null);
        setPreview({key, move, phase: accepted ? 'accepted' : 'retry'});
      }
    }
  }

  return {active, complete, attempts, legalMoves, shownMove, busy, phase, inPractice: eligible && (active || !!currentPreview),
    animation: currentPreview ? {uci: phase === 'replaying' ? original : currentPreview.move.uci, reverse: phase === 'reverting'} : undefined,
    checking: pendingKey === key, justCompleted: revealedKey === key,
    inputDisabled: !active || transitioning || busy || pendingKey !== null || !legalMoves.length,
    error: error?.key === key ? error.message : '', loading: active && context?.key !== key,
    retry: () => setRevision(value => value + 1), attemptMove};
}
