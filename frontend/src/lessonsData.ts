export type ErrorCounts = { inaccuracy: number; mistake: number; blunder: number; total: number };
export type LessonCategory = {
  key: string; label: string; counts: ErrorCounts;
  subcategories: { key: string; label: string; counts: ErrorCounts }[];
};
export type LessonAnalytics = {
  username: string; imported_games: number; analyzed_games: number; analyzed_moves: number;
  errors: ErrorCounts; categories: LessonCategory[]; unclassified: ErrorCounts; pending_reviews: number; outdated_reviews: number;
};

export function lessonCoverage(data: LessonAnalytics) {
  return `${data.analyzed_games} of ${data.imported_games} games analyzed · ${data.analyzed_moves} moves checked`;
}
