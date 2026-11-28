import { api } from './types.ts';

export const motifs = ['hanging_piece', 'fork', 'pin_skewer', 'discovered_attack'] as const;
export const contexts = ['Attack', 'Defend', 'Improve', 'Convert'] as const;
export const pieces = ['pawn', 'knight', 'bishop', 'rook', 'queen', 'king'] as const;
export const outlooks = ['Losing', 'Worse', 'Equal', 'Better', 'Winning'] as const;
export const phases = ['Opening', 'Middlegame', 'Endgame'] as const;
export const sharpness = ['Forgiving', 'Flexible', 'Selective', 'Demanding', 'Critical'] as const;
type Counts = Record<string, number>;
export type AnalyticsSummary = {
  tactical: Counts; decision_context: Counts;
  piece_comparison: { counts: Record<string, Counts> };
  context_outlook: { counts: Record<string, Counts> };
  phase: Counts; sharpness: Counts; outlook: Counts;
};
export type TimeControlSummary = AnalyticsSummary & { time_class: string; time_control_raw: string };
export type AnalyticsData = {
  username: string; updated_at: string | null; calculation_version: number;
  time_controls: TimeControlSummary[];
};

export function emptySummary(): AnalyticsSummary {
  return { tactical: {}, decision_context: {}, phase: {}, sharpness: {}, outlook: {},
    piece_comparison: {counts: Object.fromEntries(pieces.map(piece => [piece, Object.fromEntries(pieces.map(other => [other, 0]))]))},
    context_outlook: {counts: Object.fromEntries(outlooks.map(outlook => [outlook, Object.fromEntries(contexts.map(context => [context, 0]))]))} };
}

export function combineAnalytics(rows: TimeControlSummary[]): AnalyticsSummary {
  const result = emptySummary();
  for (const row of rows) {
    for (const name of ['tactical', 'decision_context', 'phase', 'sharpness', 'outlook'] as const) {
      for (const [key, value] of Object.entries(row[name])) result[name][key] = (result[name][key] ?? 0) + value;
    }
    for (const name of ['piece_comparison', 'context_outlook'] as const) {
      for (const [outer, inner] of Object.entries(row[name].counts)) {
        for (const [key, value] of Object.entries(inner)) result[name].counts[outer][key] += value;
      }
    }
  }
  return result;
}

export function ratePoints(counts: Counts, categories: readonly string[]) {
  return categories.map(label => {
    const errors = counts[`${label.toLowerCase()}_errors`] ?? 0;
    const moves = counts[`${label.toLowerCase()}_moves`] ?? 0;
    return { label, errors, moves, rate: moves ? errors / moves * 100 : null };
  });
}

export function groupedOutlook(counts: Record<string, Counts>) {
  return [['Losing', ['Losing', 'Worse']], ['Equal', ['Equal']], ['Winning', ['Better', 'Winning']]]
    .map(([label, members]) => ({ label: label as string,
      values: contexts.map(context => (members as string[]).reduce((sum, outlook) => sum + (counts[outlook]?.[context] ?? 0), 0)) }));
}

export const analyticsUpdatedEvent = 'chess-analytics-updated';
const pending = new Map<string, Promise<AnalyticsData>>();

export function refreshAnalytics(username: string): Promise<AnalyticsData> {
  const existing = pending.get(username);
  if (existing) return existing;
  const request = api<AnalyticsData>(`/api/analytics/refresh?username=${encodeURIComponent(username)}`, {method: 'POST'})
    .then(data => { window.dispatchEvent(new CustomEvent(analyticsUpdatedEvent, {detail: data})); return data; })
    .finally(() => { pending.delete(username); });
  pending.set(username, request);
  return request;
}
