export type Game = {
  id: string; url: string; white: string; black: string;
  white_rating: number | null; black_rating: number | null;
  result: string; end_time: number; time_class: string; time_control: string;
  opening: string; eco: string; ply_count: number;
  analysis?: GameAnalysisSummary | null;
};
export type Position = { fen: string; last_move: string[] | null; check_square: string | null };
export type Move = { ply: number; san: string; uci: string; color: string; number: number };
export type GameDetail = Game & { pgn: string; positions: Position[]; moves: Move[]; coach_responses: Record<string, CoachResponse>; engine_analyses?: Partial<Record<'white' | 'black', GameAnalysis>> };
export type Profile = { username: string; last_synced: number; game_count: number };
export type ImportJob = { id: string; username: string; status: 'queued' | 'running' | 'completed' | 'failed'; found: number; added: number; skipped: number; message: string };
export type EngineMove = {
  uci: string; san: string; rank: number | null; depth: number;
  score: { cp: number | null; mate: number | null; bound: 'exact' | 'lower' | 'upper' };
};
export type EngineAnalysis = {
  engine: string;
  perspective: 'White' | 'Black';
  played_move: EngineMove;
  top_moves?: EngineMove[];
  move_quality?: {
    status: 'good' | 'inaccuracy' | 'mistake' | 'blunder' | 'uncertain';
    winning_chances_loss_pp: number | null;
    reason?: string;
  };
};
export type CandidateMove = { uci: string; reason: string; highlight_squares: [string, string] };
export type MoveQuality = NonNullable<EngineAnalysis['move_quality']>['status'];
export type EngineReview = { fen: string; played_move: string; stockfish: EngineAnalysis };
export type GameAnalysisSummary = {
  game_id: string; player_color: 'white' | 'black';
  status: 'queued' | 'running' | 'completed' | 'failed' | 'interrupted';
  total: number; completed: number; counts: Partial<Record<MoveQuality, number>>;
  coach_total: number; coach_completed: number;
  error: string | null; updated_at: string;
};
export type GameAnalysis = GameAnalysisSummary & { moves: Record<string, EngineReview> };
export type PieceType = 'pawn' | 'knight' | 'bishop' | 'rook' | 'queen' | 'king';
export type MistakeClassification =
  | { category: 'tactical_miss' | 'tactical_allowed'; subcategory: 'hanging_piece' | 'fork' | 'pin_skewer' | 'discovered_attack' }
  | { category: 'positional'; subcategory: PieceType; best_move_piece?: PieceType; played_piece?: PieceType; same_piece?: boolean };
export type PositionTeaching = {
  position_overview?: string | null;
  position_explanation?: string;
  positional_thesis?: string;
  candidate_moves: CandidateMove[];
  move_evaluation?: {
    plan_alignment: 'aligned' | 'partially_aligned' | 'alternative_plan' | 'not_aligned' | 'unclear';
    explanation: string | null;
    better_candidate_uci: string | null;
    mistake_classification?: MistakeClassification | null;
  } | null;
};
export type DecisionClassification = 'forgiving' | 'flexible' | 'selective' | 'demanding' | 'critical';
export type PositionEvidence = {
  decision_classification: DecisionClassification | null;
  unclassified_reason: 'terminal_position' | 'single_legal_move' | 'fewer_than_five_legal_moves' | 'insufficient_engine_evidence' | null;
  sharpness?: { version: number; raw_cp: number | null; score: number | null; cap_cp: number; a_cp: number; cutoff_cp: number };
  delta_cp: number | null;
  delta_e_pp: number | null;
  top_moves: EngineMove[];
};
export type CoachResponse = {
  fen: string; played_move: string | null; text: string; model: string; response_id: string; created_at: string;
  stockfish?: EngineAnalysis | null;
  teaching?: PositionTeaching | null;
  move_lines?: Record<string, {san: string[]; positions: Position[]}>;
  classification_current?: boolean;
  classification_version?: number | null;
  sharpness_current?: boolean;
  sharpness_version?: number | null;
  position_evidence?: PositionEvidence | null;
  candidate_san?: Record<string, string>;
};

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
