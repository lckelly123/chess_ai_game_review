import { useId, useMemo } from 'react';
import Markdown from 'react-markdown';
import { ArrowUpRight, Check, ChevronDown } from 'lucide-react';
import type { CoachResponse, EngineReview, Move } from './types';
import { engineEvaluation, parseCoachContent } from './coachContent';
import { coachMoves } from './coachMoves';
import { engineMoves, qualityLabels } from './engineReview';
import { positionDecision } from './positionDecision';
import { moveReferences } from './moveReferences';
import { tacticSummary } from './tacticClassification';

function Prose({ children }: { children: string }) {
  return <div className="coach-prose"><Markdown skipHtml disallowedElements={['img']} components={{ h1: 'h4', h2: 'h4', h3: 'h4' }}>{children}</Markdown></div>;
}

const mateQualityDescriptions: Record<string, string> = {
  mate_created: 'Allows a forced checkmate against you.',
  mate_lost: 'Gives up a forced checkmate.',
  mate_retained: 'Keeps a forced checkmate.',
  already_forced_loss: 'The engine already found a forced loss; no new error is assigned.',
};

export default function CoachCards({ response, engineReview, engineMode = false, nextMove, pending, selectedUci, onSelectCandidate, transitioning, linePly = 0, onSelectLinePly }: {
  response?: CoachResponse; engineReview?: EngineReview; engineMode?: boolean; nextMove?: Move; pending: boolean;
  selectedUci?: string; onSelectCandidate: (uci: string) => void; transitioning: boolean;
  linePly?: number; onSelectLinePly?: (ply: number) => void;
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
  const betterUci = ['inaccuracy', 'mistake', 'blunder'].includes(quality) ? response?.better_candidate_uci : undefined;
  const waiting = pending ? 'Game analysis is in progress.' : 'Analyze this game from the library to prepare coaching for inaccuracies, mistakes, and blunders.';
  const explanation = teaching?.position_explanation ?? teaching?.positional_thesis;
  const inlineMoves = !!teaching?.position_overview && !!teaching.position_explanation;
  const selectedMove = rows.find(move => move.uci === selectedUci);
  const selectedScore = selectedMove?.engineMove ? engineEvaluation(scoreContext, selectedMove.engineMove) : null;
  const line = selectedUci ? response?.move_lines?.[selectedUci] : undefined;
  const moveRows = inlineMoves ? rows.filter(move => move.isPlayed) : rows;
  const tactics = tacticSummary(response, engineReview);

  return <div className="coach-cards">
    <div className="coach-card-body" aria-busy={pending}>
      {(response?.coach_current === false || response?.classification_current === false) && <p className="coach-placeholder">This saved review uses an earlier coach.</p>}
      {response?.coach_current !== false && response?.classification_current !== false && response?.sharpness_current === false && <p className="coach-placeholder">This saved coaching uses earlier position labels.</p>}
      {teaching && !teaching.position_overview && <p className="coach-placeholder">This saved review has no practice summary.</p>}
      {!engineOnly && <>
      <section className="coach-section" aria-labelledby={`${id}-understand-title`}>
        <div className="coach-section-heading">
          <h3 id={`${id}-understand-title`}>Understand the position</h3>
          {decision && <span className={`decision-tag ${decision.className}`} tabIndex={0} aria-label={`${decision.label}: ${decision.tooltip}`}>
            {decision.label}<span className="coach-tooltip" aria-hidden="true">{decision.tooltip}</span>
          </span>}
        </div>
        {teaching ? <>
          <p className="teaching-paragraph">{moveReferences(explanation ?? '', rows).map((part, index) => part.move
            ? <button key={index} type="button" className="inline-move" disabled={transitioning}
                aria-label={`${selectedUci === part.move.uci ? 'Hide' : 'Show'} explanation for ${part.text}`}
                aria-expanded={selectedUci === part.move.uci} aria-controls={`${id}-move-detail`}
                onClick={() => onSelectCandidate(part.move!.uci)}>{part.text}</button>
            : part.text)}</p>
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
        </> : <p className="coach-placeholder">{waiting} The position explanation will appear here.</p>}
      </section>
      </>}
      {(!inlineMoves || moveRows.length > 0) && <section className="coach-section coach-moves-section" aria-labelledby={`${id}-moves-title`}>
        <div className="coach-section-heading moves-heading"><h3 id={`${id}-moves-title`}>{inlineMoves ? 'Your move' : 'Moves'}</h3></div>
        {moveRows.length ? <div className="candidate-moves" role="group" aria-label={inlineMoves ? 'Player move' : 'Candidate moves and player move'}>
          {moveRows.map(move => {
            const selected = selectedUci === move.uci;
            const score = move.engineMove ? engineEvaluation(scoreContext, move.engineMove) : null;
            return <div className={`candidate-row${move.isPlayed ? ' player-move-row' : ''}`} key={move.uci} data-uci={move.uci}>
              <button type="button" className="candidate-move" aria-label={`${selected ? 'Hide' : 'Show'} explanation for ${move.san}${move.isPlayed ? ', player move' : ''}`} aria-expanded={selected} aria-controls={`${id}-move-detail`} aria-pressed={selected} disabled={transitioning} onClick={() => onSelectCandidate(move.uci)}>
                <span className="candidate-heading">
                  <span className="move-labels"><strong>{move.san}</strong>
                    {move.isPlayed && <><span className="player-move-badge">Player move</span><span className={`move-quality ${quality}`} title={qualityDescription} aria-label={`${qualityLabel}. ${qualityDescription}`}>{quality === 'good' && <Check size={12} aria-hidden="true"/>}{qualityLabel}</span></>}
                  </span>
                  <span className="candidate-meta">
                    {score && <span id={`${id}-${move.uci}-score`} className={`engine-score ${score.tone}`} title={`${score.label} · ${score.perspective}'s perspective · depth ${move.engineMove?.depth}`} aria-label={`Evaluation ${score.value}, ${score.label}, ${score.perspective}'s perspective`}>{score.value}</span>}
                    <span className="move-board-action" title={selected ? 'Shown on board' : 'Show on board'}>{selected ? <Check size={15} aria-hidden="true"/> : <ArrowUpRight size={15} aria-hidden="true"/>}</span>
                  </span>
                </span>
              </button>
            </div>;
          })}
        </div> : <p className="coach-placeholder">{engineOnly ? nextMove ? 'No saved engine analysis for this position.' : 'No recorded move remains.' : positionEvidence?.unclassified_reason === 'terminal_position' ? 'This position has ended.' : response ? 'No candidate moves are included in this saved response.' : 'Candidate moves and player feedback will appear here.'}</p>}
        {response && !response.played_move && <p className="move-empty-note">{moveFeedback?.explanation ?? (nextMove ? 'No saved feedback is available for the recorded move.' : 'No recorded move is available to evaluate.')}</p>}
      </section>}
      <div id={`${id}-move-detail`}>
        {selectedMove && <section className="move-detail" aria-label={`${selectedMove.san} explanation`}>
          <div className="candidate-heading">
            <h3>{selectedMove.san}{selectedMove.isPlayed && <span className="player-move-badge">Player move</span>}</h3>
            {selectedScore && <span className={`engine-score ${selectedScore.tone}`} title={`${selectedScore.label} · ${selectedScore.perspective}'s perspective`}>{selectedScore.value}</span>}
          </div>
          {selectedMove.reason && <p className="candidate-reason">{selectedMove.reason}</p>}
          {selectedMove.feedback && selectedMove.feedback !== selectedMove.reason && <p className="candidate-feedback">{selectedMove.feedback}</p>}
          {selectedMove.isPlayed && betterUci && <button className="better-candidate" type="button" disabled={transitioning} onClick={() => onSelectCandidate(betterUci)}>
            Compare with {response?.candidate_san?.[betterUci] ?? betterUci} <ArrowUpRight size={14} aria-hidden="true"/>
          </button>}
          {line && onSelectLinePly && <div className="engine-line" role="group" aria-label="Explore engine continuation">
            <p>Engine continuation</p>
            <div className="line-moves">
              <button type="button" disabled={transitioning} aria-pressed={linePly === 0} onClick={() => onSelectLinePly(0)}>Position</button>
              {line.san.map((san, index) => <button type="button" key={index} disabled={transitioning}
                aria-label={`Show ${san}, step ${index + 1}`} aria-pressed={linePly === index + 1} onClick={() => onSelectLinePly(index + 1)}>{san}</button>)}
            </div>
          </div>}
        </section>}
      </div>
      {tactics && <p className="tactic-classification"><span>Tactic classification:</span> {tactics}</p>}
    </div>
  </div>;
}
