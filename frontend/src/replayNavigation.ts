import type { Position } from './types.ts';

export const BETWEEN_TURNS_MS = 100;
export const AUTOPLAY_TURN_MS = 850;

export type ReplayTransition = { via: number; to: number };
export type ReplayNavigation = {
  stops: number[];
  ply: number;
  transition: ReplayTransition | null;
  playing: boolean;
};
export type ReplayAction =
  | { type: 'step'; direction: 1 | -1; animate: boolean; automatic?: boolean }
  | { type: 'settle'; transition: ReplayTransition }
  | { type: 'seek'; ply: number }
  | { type: 'toggle-play' }
  | { type: 'pause' };

export function playerTurnStops(positions: Position[], isWhite: boolean): number[] {
  const color = isWhite ? 'w' : 'b';
  // Use the FEN turn, so games starting from a custom position work too.
  return positions.flatMap((position, ply) =>
    ply === 0 || ply === positions.length - 1 || position.fen.split(' ')[1] === color ? [ply] : []);
}

export function restoreReplay(stops: number[], savedPly: number): ReplayNavigation {
  const requested = Number.isFinite(savedPly) ? savedPly : 0;
  // Older bookmarks may be on an opponent's turn. Return to the preceding
  // decision point instead of skipping ahead past the player's decision.
  let ply = stops[0];
  for (const stop of stops) {
    if (stop > requested) break;
    ply = stop;
  }
  return { stops, ply, transition: null, playing: false };
}

export function replayNavigation(state: ReplayNavigation, action: ReplayAction): ReplayNavigation {
  const last = state.stops[state.stops.length - 1];
  switch (action.type) {
    case 'step': {
      if (action.automatic && !state.playing) return state;
      // A second click advances from the pending destination, not the brief
      // intermediate board or a stale render of the last settled position.
      const from = state.transition?.to ?? state.ply;
      const index = state.stops.indexOf(from) + action.direction;
      if (index < 0 || index >= state.stops.length) return { ...state, playing: false };
      const to = state.stops[index];
      const playing = !!action.automatic && state.playing;
      if (action.animate && Math.abs(to - from) > 1) {
        return { ...state, playing, transition: { via: from + action.direction, to } };
      }
      return { ...state, ply: to, transition: null, playing: playing && to !== last };
    }
    case 'settle':
      // A cancelled timeout can already be queued. Ignore it after a seek,
      // reversal, or newer step, even if its destination happens to match.
      return state.transition === action.transition
        ? { ...state, ply: action.transition.to, transition: null, playing: state.playing && action.transition.to !== last }
        : state;
    case 'seek':
      return restoreReplay(state.stops, action.ply);
    case 'toggle-play':
      return { ...state, playing: !state.playing, ...(state.ply === last && !state.transition ? { ply: state.stops[0] } : {}) };
    case 'pause':
      // Finish an in-flight pair before resting; never strand the board on
      // the opponent's turn when autoplay is paused during the brief preview.
      return { ...state, playing: false };
  }
}
