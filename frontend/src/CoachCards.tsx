import { useId, useMemo } from 'react';
import Markdown from 'react-markdown';
import { ArrowUpRight, Check, ChevronDown } from 'lucide-react';
import type { CoachResponse, EngineReview, Move } from './types';
import { engineEvaluation, parseCoachContent } from './coachContent';
import { coachMoves } from './coachMoves';
import { engineMoves, qualityLabels } from './engineReview';
import { positionDecision } from './positionDecision';

function Prose({ children }: { children: string }) {
  return <div className="coach-prose"><Markdown skipHtml disallowedElements={['img']} components={{ h1: 'h4', h2: 'h4', h3: 'h4' }}>{children}</Markdown></div>;
}

const mistakeCategories = { tactical_miss: 'Missed tactic', tactical_allowed: 'Allowed tactic', positional: 'Positional' };
const mistakeSubcategories = {
  hanging_piece: 'Hanging piece', fork: 'Fork', pin_skewer: 'Pin / skewer', discovered_attack: 'Discovered attack',
  pawn: 'Best move: pawn', knight: 'Best move: knight', bishop: 'Best move: bishop',
  rook: 'Best move: rook', queen: 'Best move: queen', king: 'Best move: king',
};
const mateQualityDescriptions: Record<string, string> = {
  mate_created: 'Allows a forced checkmate against you.',
  mate_lost: 'Gives up a forced checkmate.',
  mate_retained: 'Keeps a forced checkmate.',
  already_forced_loss: 'The engine already found a forced loss; no new error is assigned.',
};

export default function CoachCards({ response, engineReview, engineMode = false, nextMove, pending, selectedUci, onSelectCandidate, transitioning }: {
  response?: CoachResponse; engineReview?: EngineReview; engineMode?: boolean; nextMove?: Move; pending: boolean;
  selectedUci?: string; onSelectCandidate: (uci: string) => void; transitioning: boolean;
}) {
  const id = useId();
  const content = useMemo(() => parseCoachContent(response?.text ?? ''), [response?.text]);
  const engineOnly = !response && (engineMode || !!engineReview);
  const engine = response ? response.stockfish : engineReview?.stockfish;
  const teaching = response?.teaching;
  const positionEvidence = response?.position_evidence;
  const decision = positionDecision(positionEvidence);
  const rows = engineOnly ? engineMoves(engineReview) : coachMoves(response);
  const scoreContext = engine ?? (response ? { perspective: response.fen.split(' ')[1] === 'w' ? 'White' as const : 'Black' as const } : undefined);
  const moveFeedback = teaching?.move_evaluation;
  const quality = engine?.move_quality?.status ?? 'uncertain';
  const qualityLabel = qualityLabels[quality] ?? qualityLabels.uncertain;
  const qualityLoss = engine?.move_quality?.winning_chances_loss_pp;
  const qualityDescription = qualityLoss != null
    ? `Winning chances lost: ${qualityLoss.toFixed(2)} percentage points from your perspective. Less than 5: Good; 5 to less than 10: Inaccuracy; 10 to less than 15: Mistake; 15 or more: Blunder.`
    : mateQualityDescriptions[engine?.move_quality?.reason ?? ''] ?? 'The available engine scores do not support a reliable comparison.';
  const betterUci = ['inaccuracy', 'mistake', 'blunder'].includes(quality) ? moveFeedback?.better_candidate_uci : undefined;
  const mistake = ['inaccuracy', 'mistake', 'blunder'].includes(quality) ? moveFeedback?.mistake_classification : undefined;
  const waiting = pending ? 'Your coach is thinking…' : 'Run coach to explore this position.';

  return <div className="coach-cards">
    <div className="coach-card-body" aria-busy={pending}>
      {response?.classification_current === false && <p className="coach-placeholder">This saved review uses an earlier coach. Run coach to update its analysis and lesson labels.</p>}
      {response?.classification_current !== false && response?.sharpness_current === false && <p className="coach-placeholder">This saved coaching used earlier position labels. Run coach to refresh its explanation.</p>}
      {!engineOnly && <>
      <section className="coach-section" aria-labelledby={`${id}-understand-title`}>
        <div className="coach-section-heading">
          <h3 id={`${id}-understand-title`}>Understand the position</h3>
          {decision && <span className={`decision-tag ${decision.className}`} tabIndex={0} aria-label={`${decision.label}: ${decision.tooltip}`}>
            {decision.label}<span className="coach-tooltip" aria-hidden="true">{decision.tooltip}</span>
          </span>}
        </div>
        {teaching ? <>
          <p className="teaching-paragraph">{teaching.positional_thesis}</p>
        </> : response ? <>
          {!!content.positionIntro && <Prose>{content.positionIntro.replace(/^\s*\*\*Position character:\*\*[^\n]*(?:\n|$)/gim, '').trim()}</Prose>}
          {content.factors.length > 0 && <>
            <p className="factor-hint">Ranked factors <span>Expand to read the reasoning</span></p>
            <div className="position-factors">
              {content.factors.map((factor, index) => <details className="position-factor" key={`${index}:${factor.title}`}>
                <summary><span className="factor-rank" aria-label={`Rank ${index + 1}`}>{index + 1}</span><span>{factor.title}</span><ChevronDown size={16} aria-hidden="true"/></summary>
                <div className="factor-explanation"><Prose>{factor.body}</Prose></div>
              </details>)}
            </div>
          </>}
          {content.thesis && <div className="coach-subsection positional-thesis"><h4>Positional thesis</h4><Prose>{content.thesis}</Prose></div>}
        </> : <p className="coach-placeholder">{waiting} Its classification and positional thesis will appear here.</p>}
      </section>
      <section className="coach-section" aria-labelledby={`${id}-plan-title`}>
        <h3 id={`${id}-plan-title`}>{teaching ? 'Needs of the position' : 'Develop a plan'}</h3>
        {teaching ? <p className="teaching-paragraph">{teaching.needs_of_position}</p> : <>
        {content.planIntro && <Prose>{content.planIntro}</Prose>}
        {content.objective && <div className="coach-subsection"><h4>Strategic objective</h4><Prose>{content.objective}</Prose></div>}
        {content.approach && <div className="coach-subsection"><h4>How to approach the position</h4><Prose>{content.approach}</Prose></div>}
        {!content.planIntro && !content.objective && !content.approach && <p className="coach-placeholder">{response ? 'No plan is included in this saved response.' : 'The needs of the position and candidate moves will appear here.'}</p>}
        </>}
      </section>
      </>}
      <section className="coach-section coach-moves-section" aria-labelledby={`${id}-moves-title`}>
        <div className="coach-section-heading moves-heading"><h3 id={`${id}-moves-title`}>Moves</h3></div>
        {rows.length ? <div className="candidate-moves" role="group" aria-label="Candidate moves and player move">
          {rows.map(move => {
            const selected = selectedUci === move.uci;
            const score = move.engineMove ? engineEvaluation(scoreContext, move.engineMove) : null;
            return <div className={`candidate-row${move.isPlayed ? ' player-move-row' : ''}`} key={move.uci} data-uci={move.uci}>
              <button type="button" className="candidate-move" aria-label={`${selected ? 'Hide' : 'Show'} ${move.san} on board${move.isPlayed ? ', player move' : ''}`} aria-describedby={[move.reason && `${id}-${move.uci}-reason`, score && `${id}-${move.uci}-score`, move.isPlayed && mistake && `${id}-mistake`].filter(Boolean).join(' ') || undefined} aria-pressed={selected} disabled={transitioning} onClick={() => onSelectCandidate(move.uci)}>
                <span className="candidate-heading">
                  <span className="move-labels"><strong>{move.san}</strong>
                    {move.isPlayed && <><span className="player-move-badge">Player move</span><span className={`move-quality ${quality}`} title={qualityDescription} aria-label={`${qualityLabel}. ${qualityDescription}`}>{quality === 'good' && <Check size={12} aria-hidden="true"/>}{qualityLabel}</span></>}
                  </span>
                  <span className="candidate-meta">
                    {score && <span id={`${id}-${move.uci}-score`} className={`engine-score ${score.tone}`} title={`${score.label} · ${score.perspective}'s perspective · depth ${move.engineMove?.depth}`} aria-label={`Evaluation ${score.value}, ${score.label}, ${score.perspective}'s perspective`}>{score.value}</span>}
                    <span className="move-board-action" title={selected ? 'Shown on board' : 'Show on board'}>{selected ? <Check size={15} aria-hidden="true"/> : <ArrowUpRight size={15} aria-hidden="true"/>}</span>
                  </span>
                </span>
                {move.reason && <span className="candidate-reason" id={`${id}-${move.uci}-reason`}>{move.reason}</span>}
                {move.feedback && move.feedback !== move.reason && <span className="candidate-feedback">{move.feedback}</span>}
                {move.isPlayed && mistake && <span className="mistake-classification" id={`${id}-mistake`}>
                  <span className="mistake-category">{mistakeCategories[mistake.category]}</span>
                  {mistake.subcategory && <span className="mistake-subcategory">{mistakeSubcategories[mistake.subcategory]}</span>}
                </span>}
              </button>
              {move.isPlayed && betterUci && <button className="better-candidate" type="button" disabled={transitioning} onClick={() => onSelectCandidate(betterUci)}>
                Compare with {response?.candidate_san?.[betterUci] ?? betterUci} <ArrowUpRight size={14} aria-hidden="true"/>
              </button>}
            </div>;
          })}
        </div> : <p className="coach-placeholder">{engineOnly ? nextMove ? 'No saved engine analysis for this position.' : 'No recorded move remains.' : positionEvidence?.unclassified_reason === 'terminal_position' ? 'This position has ended.' : response ? 'No candidate moves are included in this saved response.' : 'Candidate moves and player feedback will appear here.'}</p>}
        {response && !response.played_move && <p className="move-empty-note">{moveFeedback?.explanation ?? (nextMove ? 'Run coach for feedback on the recorded move.' : 'No recorded move is available to evaluate.')}</p>}
      </section>
    </div>
  </div>;
}
