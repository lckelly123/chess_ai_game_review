import type { Move } from './types';
import { qualityLabels } from './engineReview';
import type { useReviewPractice } from './useReviewPractice';

export default function PracticeCard({ practice, original, previous }: {
  practice: ReturnType<typeof useReviewPractice>; original: Move; previous?: Move;
}) {
  const last = practice.attempts.at(-1);
  const message = practice.checking ? 'Checking your move…'
    : practice.complete ? 'Good move. You found an alternative.'
      : last?.quality === 'uncertain' ? 'This move could not be graded reliably. Try again.'
        : last?.status === 'error' ? 'The last attempt was not graded. Try again.'
          : last?.quality ? `${qualityLabels[last.quality]}. Try another move.`
            : 'Select a piece, then its destination.';
  return <section className="practice-card" aria-label="Find a good move">
    <h3>{practice.complete ? 'Exercise complete' : 'Find a good move'}</h3>
    <p>{previous ? <>Opponent played <strong>{previous.san}</strong>. </> : 'Starting position. '}You played <strong>{original.san}</strong>.</p>
    {!practice.complete && <p>Find any move better than an inaccuracy. It doesn’t have to be the best move.</p>}
    <p className="practice-feedback" role="status">{practice.loading && !practice.error ? 'Loading legal moves…' : message}</p>
    {practice.error && <p className="coach-error" role="alert">{practice.error} {practice.loading && <button type="button" className="text-button" onClick={practice.retry}>Retry</button>}</p>}
    {practice.complete && practice.shownMove && <button type="button" className="secondary-button" onClick={practice.showReview}>View review</button>}
    {!!practice.attempts.length && <details className="practice-history" open={!practice.complete}>
      <summary>{practice.attempts.length} {practice.attempts.length === 1 ? 'attempt' : 'attempts'}</summary>
      <ol>{practice.attempts.map((attempt, index) => <li key={`${index}:${attempt.at}`}>
        <strong>{attempt.san}</strong><span>{attempt.status === 'checking' ? 'Checking…' : attempt.quality ? qualityLabels[attempt.quality] : 'Not graded'}</span>
      </li>)}</ol>
    </details>}
  </section>;
}
