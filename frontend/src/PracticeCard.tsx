import { qualityLabels } from './engineReview';
import type { Move } from './types';
import type { useReviewPractice } from './useReviewPractice';

export default function PracticeCard({ practice, original, overview }: {
  practice: ReturnType<typeof useReviewPractice>; original: Pick<Move, 'san'>; overview?: string | null;
}) {
  const title = `Find a better move than ${original.san}`;
  const last = practice.attempts.at(-1);
  const message = practice.checking ? 'Checking your move…'
    : practice.complete ? 'Good move. You found an alternative.'
      : last?.quality === 'uncertain' ? 'This move could not be graded reliably. Try again.'
        : last?.status === 'error' ? 'The last attempt was not graded. Try again.'
          : last?.quality ? `${qualityLabels[last.quality]}. Try another move.`
            : '';
  return <div className="practice-panel">
    <section className="practice-card" aria-label={title}>
      <h3>{title}</h3>
      {overview && <p className="practice-overview">{overview}</p>}
    </section>
    <p className={message && !practice.error ? 'practice-feedback' : 'visually-hidden'} role="status">{practice.error ? '' : practice.loading ? 'Loading legal moves…' : message}</p>
    {practice.error && <p className="coach-error" role="alert">{practice.error} {practice.loading && <button type="button" className="text-button" onClick={practice.retry}>Retry</button>}</p>}
    {practice.complete && practice.shownMove && <button type="button" className="secondary-button" onClick={practice.showReview}>View review</button>}
  </div>;
}
