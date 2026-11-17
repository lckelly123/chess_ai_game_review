export type Game = {
  id: string; url: string; white: string; black: string;
  white_rating: number | null; black_rating: number | null;
  result: string; end_time: number; time_class: string; time_control: string;
  opening: string; eco: string; ply_count: number;
};
export type Position = { fen: string; last_move: string[] | null; check_square: string | null };
export type Move = { ply: number; san: string; uci: string; color: string; number: number };
export type GameDetail = Game & { pgn: string; positions: Position[]; moves: Move[]; coach_responses: Record<string, CoachResponse> };
export type Profile = { username: string; last_synced: number; game_count: number };
export type ImportJob = { id: string; username: string; status: 'queued' | 'running' | 'completed' | 'failed'; found: number; added: number; skipped: number; message: string };
export type CoachResponse = { fen: string; played_move: string | null; text: string; model: string; response_id: string; created_at: string };

export function perspective(game: Game, username: string) {
  const isWhite = game.white.toLowerCase() === username.toLowerCase();
  const result = game.result === '1/2-1/2' ? 'draw' : (game.result === '1-0') === isWhite ? 'win' : 'loss';
  return { isWhite, result, opponent: isWhite ? game.black : game.white, opponentRating: isWhite ? game.black_rating : game.white_rating };
}

export function timeControl(value: string) {
  if (value.includes('/')) return `${Math.round(Number(value.split('/')[1]) / 86400)}d / move`;
  const [base, increment] = value.split('+').map(Number);
  if (!Number.isFinite(base)) return value;
  return `${base / 60}${increment ? ` + ${increment}` : ''}`;
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); } catch { throw new Error('The app server is unavailable. Please try again.'); }
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'The request failed. Please try again.');
  return data as T;
}

export function readStored(key: string): string {
  try { return localStorage.getItem(key) || ''; } catch { return ''; }
}
export function store(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* Storage can be disabled; replay still works. */ }
}
