import { useRef } from 'react';
import { qualityLabels } from './engineReview';
import { useCoachSpeech } from './useCoachSpeech';
import type { Move } from './types';
import type { useReviewPractice } from './useReviewPractice';

export default function PracticeCard({ practice, original, overview, speechId = '', reducedMotion = false }: {
  practice: ReturnType<typeof useReviewPractice>; original: Pick<Move, 'san'>; overview?: string | null;
  speechId?: string; reducedMotion?: boolean;
}) {
  const title = `Find a better move than ${original.san}`;
  const card = useRef<HTMLElement>(null);
  const speech = useCoachSpeech({id: `${speechId}:hint:${original.san}`, children: overview, reducedMotion, immediate: practice.complete});
  const last = practice.attempts.at(-1);
  const message = practice.checking ? 'Checking your move…'
    : practice.complete ? 'Good move. Let’s look at why.'
      : last?.quality === 'uncertain' ? 'This move could not be graded reliably. Try again.'
        : last?.status === 'error' ? 'The last attempt was not graded. Try again.'
          : last?.quality ? `${qualityLabels[last.quality]}. Try another move.`
            : '';
  return <div className="practice-panel">
    <section className="practice-card" aria-label={title} ref={card} tabIndex={-1}>
      <div className="practice-card-heading"><h3>{title}</h3>
        {speech.speaking && <button type="button" className="coach-show-all" aria-label="Show full position hint" onClick={() => {
          card.current?.focus({preventScroll: true}); speech.showAll();
        }}>Show all</button>}
      </div>
      {overview && <p className="practice-overview">{speech.content}</p>}
    </section>
    <p className={message && !practice.error ? 'practice-feedback' : 'visually-hidden'} role="status">{practice.error ? '' : practice.loading ? 'Loading legal moves…' : message}</p>
    {practice.error && <p className="coach-error" role="alert">{practice.error} {practice.loading && <button type="button" className="text-button" onClick={practice.retry}>Retry</button>}</p>}
  </div>;
}
