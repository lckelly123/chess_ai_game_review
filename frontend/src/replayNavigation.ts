import type { Position } from './types.ts';

export const AUTOPLAY_TURN_MS = 850;

export type ReplayNavigation = {
  stops: number[];
  ply: number;
  playing: boolean;
};
export type ReplayAction =
  | { type: 'step'; direction: 1 | -1; automatic?: boolean }
  | { type: 'seek'; ply: number }
  | { type: 'toggle-play' }
  | { type: 'pause' };

export const replayStops = (positions: Position[]) => positions.map((_, ply) => ply);

export function restoreReplay(stops: number[], savedPly: number): ReplayNavigation {
  const requested = Number.isFinite(savedPly) ? savedPly : 0;
  // Keep exact half-move bookmarks, including opponent turns.
  let ply = stops[0] ?? 0;
  for (const stop of stops) {
    if (stop > requested) break;
    ply = stop;
  }
  return { stops, ply, playing: false };
}

export function replayNavigation(state: ReplayNavigation, action: ReplayAction): ReplayNavigation {
  const last = state.stops.at(-1) ?? 0;
  switch (action.type) {
    case 'step': {
      if (action.automatic && !state.playing) return state;
      const ply = Math.max(0, Math.min(last, state.ply + action.direction));
      return { ...state, ply, playing: !!action.automatic && state.playing && ply < last };
    }
    case 'seek':
      return restoreReplay(state.stops, action.ply);
    case 'toggle-play':
      return { ...state, playing: !state.playing && last > 0, ply: state.ply === last ? 0 : state.ply };
    case 'pause':
      return { ...state, playing: false };
  }
}
