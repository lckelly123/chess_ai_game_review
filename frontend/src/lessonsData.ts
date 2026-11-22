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

export const lessonSeverities = ['inaccuracy', 'mistake', 'blunder'] as const;
export type LessonSeverity = typeof lessonSeverities[number];
export type LessonFilter = 'all' | LessonSeverity;
export type LessonGroup = 'positional' | 'tactical' | 'unclassified';

export function combineErrorCounts(counts: ErrorCounts[]): ErrorCounts {
  return counts.reduce((sum, count) => ({
    inaccuracy: sum.inaccuracy + count.inaccuracy,
    mistake: sum.mistake + count.mistake,
    blunder: sum.blunder + count.blunder,
    total: sum.total + count.total,
  }), { inaccuracy: 0, mistake: 0, blunder: 0, total: 0 });
}

export function lessonGroupCounts(data: LessonAnalytics): Record<LessonGroup, ErrorCounts> {
  return {
    positional: combineErrorCounts(data.categories.filter(category => category.key === 'positional').map(category => category.counts)),
    tactical: combineErrorCounts(data.categories.filter(category => ['tactical_miss', 'tactical_allowed'].includes(category.key)).map(category => category.counts)),
    unclassified: data.unclassified,
  };
}

export function filteredLessonRows(category: LessonCategory | undefined, filter: LessonFilter) {
  const key = filter === 'all' ? 'total' : filter;
  return (category?.subcategories ?? [])
    .map(row => ({ ...row, matching: row.counts[key] }))
    .filter(row => row.matching > 0)
    .sort((a, b) => b.matching - a.matching || a.label.localeCompare(b.label));
}

export function severitySummary(counts: ErrorCounts) {
  return lessonSeverities.filter(severity => counts[severity] > 0).map(severity => {
    const count = counts[severity];
    const label = count === 1 ? severity : severity === 'inaccuracy' ? 'inaccuracies' : `${severity}s`;
    return `${count.toLocaleString()} ${label}`;
  }).join(' · ') || 'No errors';
}
