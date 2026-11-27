// Synthetic Black-to-move game for replay regression checks, never library data.
const positions = [
  {fen: '1q2k3/8/8/8/8/8/8/4K3 b - - 0 12', last_move: null, check_square: null},
  {fen: '4k3/8/8/8/1q6/8/8/4K3 w - - 1 13', last_move: ['b8', 'b4'], check_square: 'e1'},
  {fen: '4k3/8/8/8/1q6/8/8/5K2 b - - 2 13', last_move: ['e1', 'f1'], check_square: null},
  {fen: '4k3/8/8/8/8/8/1q6/5K2 w - - 3 14', last_move: ['b4', 'b2'], check_square: null},
].map(position => ({...position, phase: 'endgame'}));
const moves = [
  {ply: 1, number: 12, color: 'black', san: 'Qb4+', uci: 'b8b4', elapsed_seconds: 4},
  {ply: 2, number: 13, color: 'white', san: 'Kf1', uci: 'e1f1', elapsed_seconds: 5},
  {ply: 3, number: 13, color: 'black', san: 'Qb2', uci: 'b4b2', elapsed_seconds: 6},
];
const engineMove = (uci, san) => ({uci, san, depth: 18, rank: 1, score: {cp: 500, mate: null, bound: 'exact'}});
const reviews = Object.fromEntries(moves.map((move, index) => [index, {
  fen: positions[index].fen, played_move: move.uci,
  candidate_positions: index === 0 ? {b8b2: {fen: '4k3/8/8/8/8/8/1q6/4K3 w - - 1 13', last_move: ['b8', 'b2'], check_square: null}} : {},
  stockfish: {perspective: move.color === 'white' ? 'White' : 'Black',
    top_moves: [engineMove(move.uci, move.san), ...(index === 0 ? [engineMove('b8b2', 'Qb2')] : [])],
    played_move: engineMove(move.uci, move.san), move_quality: {status: index === 1 ? 'good' : 'mistake'}},
}]));
const coach = index => ({
  ...reviews[index], response_id: `replay-fixture-${index}`, model: 'gpt-6-astra', created_at: '2026-11-26T12:00:00Z', text: '',
  candidate_san: {[moves[index].uci]: moves[index].san, b8b2: 'Qb2'},
  teaching: {position_overview: 'Consider the queen and king.', position_explanation: `Review of ${moves[index].san}. Your move was [[${moves[index].uci}]].${index === 0 ? ' Consider [[b8b2]].' : ''}`,
    candidate_moves: index === 0 ? [{uci: 'b8b2', reason: 'An alternative queen move.'}] : [],
    move_evaluation: {explanation: `Saved assessment of ${moves[index].san}.${index === 0 ? ' Line: [[Qb4+ Kf1]].' : ''}`, mistake_classification: null}},
  move_lines: index === 0 ? {b8b4: {san: ['Qb4+', 'Kf1'], uci: ['b8b4', 'e1f1'], positions: positions.slice(0, 3)}} : {},
});
export const replayGame = {
  id: 'synthetic-replay-regression', white: 'White player', black: 'Black player', white_rating: 1200, black_rating: 1200,
  result: '0-1', moves, positions, coach_responses: {0: coach(0), 2: coach(2)},
  engine_analyses: {black: {status: 'completed', total: 2, completed: 2, opponent_total: 1, opponent_completed: 1,
    coach_total: 2, coach_completed: 2, moves: {0: reviews[0], 2: reviews[2]}, opponent_moves: {1: reviews[1]}}},
};
