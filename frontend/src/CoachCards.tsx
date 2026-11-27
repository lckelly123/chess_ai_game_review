import { useId, useMemo, useRef } from 'react';
import Markdown from 'react-markdown';
import { ArrowUpRight, Check, ChevronDown } from 'lucide-react';
import type { CoachResponse, EngineReview, MistakeClassification, Move } from './types';
import { engineEvaluation, parseCoachContent } from './coachContent';
import { coachMoves } from './coachMoves';
import { acceptableQuality, engineMoves, qualityLabels } from './engineReview';
import { moveReferences } from './moveReferences';
import { pvReferences, type PvSequence } from './pvReferences';
import { useCoachSpeech } from './useCoachSpeech';

function Prose({ children }: { children: string }) {
  return <div className="coach-prose"><Markdown skipHtml disallowedElements={['img']} components={{ h1: 'h4', h2: 'h4', h3: 'h4' }}>{children}</Markdown></div>;
}

const mateQualityDescriptions: Record<string, string> = {
  mate_created: 'Allows a forced checkmate against the moving side.',
  mate_lost: 'Gives up a forced checkmate.',
  mate_retained: 'Keeps a forced checkmate.',
  already_forced_loss: 'The engine already found a forced loss; no new error is assigned.',
};

const mistakeCategoryLabels: Record<MistakeClassification['category'], string> = {
  tactical_miss: 'Missed tactic', tactical_allowed: 'Allowed tactic', positional: 'Positional',
};
const mistakeSubcategoryLabels: Record<MistakeClassification['subcategory'], string> = {
  hanging_piece: 'Hanging piece', fork: 'Fork', pin_skewer: 'Pin / skewer', discovered_attack: 'Discovered attack',
  pawn: 'Pawn', knight: 'Knight', bishop: 'Bishop', rook: 'Rook', queen: 'Queen', king: 'King',
  Attack: 'Attack', Defend: 'Defend', Improve: 'Improve', Convert: 'Convert',
};

export default function CoachCards({ response, engineReview, engineMode = false, opponent = false, reviewedMove, pending, selectedUci, onSelectCandidate, transitioning, activeSequenceId, onPlaySequence, speechId, reducedMotion = false }: {
  response?: CoachResponse; engineReview?: EngineReview; engineMode?: boolean; reviewedMove?: Move; pending: boolean;
  selectedUci?: string; onSelectCandidate: (uci: string) => void; transitioning: boolean;
  activeSequenceId?: string; onPlaySequence?: (sequence: PvSequence) => void;
  opponent?: boolean;
  speechId?: string; reducedMotion?: boolean;
}) {
  const id = useId();
  const card = useRef<HTMLDivElement>(null);
  const content = useMemo(() => parseCoachContent(response?.text ?? ''), [response?.text]);
  const engineOnly = !response && (engineMode || !!engineReview);
  const engine = response ? response.stockfish : engineReview?.stockfish;
  const teaching = response?.teaching;
  const positionEvidence = response?.position_evidence;
  const rows = engineOnly ? engineMoves(engineReview) : coachMoves(response);
  const scoreContext = engine ?? (response ? { perspective: response.fen.split(' ')[1] === 'w' ? 'White' as const : 'Black' as const } : undefined);
  const moveFeedback = teaching?.move_evaluation;
  const quality = engine?.move_quality?.status ?? 'uncertain';
  const qualityLabel = qualityLabels[quality] ?? qualityLabels.uncertain;
  const qualityLoss = engine?.move_quality?.winning_chances_loss_pp;
  const playedLabel = opponent ? 'Opponent move' : 'Player move';
  const qualityDescription = qualityLoss != null
    ? `Winning chances lost: ${qualityLoss.toFixed(2)} percentage points from ${engine?.perspective ?? 'the mover'}’s perspective. Best: matches the engine’s top raw evaluation. Otherwise, less than 2.5: Excellent; 2.5 to less than 5: Good; 5 to less than 10: Inaccuracy; 10 to less than 15: Mistake; 15 or more: Blunder.`
    : mateQualityDescriptions[engine?.move_quality?.reason ?? ''] ?? 'The available engine scores do not support a reliable comparison.';
  const waiting = pending ? 'Game analysis is in progress.' : 'Analyze this game from the library to prepare coaching for inaccuracies, mistakes, and blunders.';
  const explanation = teaching?.position_explanation ?? teaching?.positional_thesis;
  const inlineMoves = !!teaching?.position_overview && !!teaching.position_explanation;
  const selectedMove = rows.find(move => move.uci === selectedUci);
  const mistake = selectedMove?.isPlayed ? moveFeedback?.mistake_classification : undefined;
  const selectedScore = selectedMove?.engineMove ? engineEvaluation(scoreContext, selectedMove.engineMove) : null;
  const moveExplanation = (text: string) => pvReferences(text, response?.move_lines, selectedUci).map((part, index) =>
    part.sequence && onPlaySequence
      ? <button key={index} type="button" className="inline-move inline-pv" disabled={transitioning}
          aria-label={`Play variation ${part.text}`} aria-pressed={activeSequenceId === part.sequence.id}
          onClick={() => onPlaySequence(part.sequence!)}>{part.text}</button>
      : part.text);
  const paragraphs = (explanation ?? '').split(/\r?\n\s*\r?\n/).map(text => text.trim()).filter(Boolean);
  // Older saved reviews may predate the final player-move paragraph. Keep the
  // move accessible without inventing a comparison or making another model call.
  if (inlineMoves && response?.played_move && !moveReferences(explanation ?? '', rows).some(part => part.move?.isPlayed)) {
    paragraphs.push(`Your move was [[${response.played_move}]].`);
  }
  const speechKey = speechId ?? `${response?.fen}:${response?.response_id}`;
  const positionSpeech = useCoachSpeech({id: `${speechKey}:position`, reducedMotion,
    children: paragraphs.map((paragraph, paragraphIndex) => <p key={paragraphIndex} className="teaching-paragraph">{moveReferences(paragraph, rows).map((part, index) => part.move
      ? <button key={index} type="button" className="inline-move" disabled={transitioning}
          aria-label={`${selectedUci === part.move.uci ? 'Hide' : 'Show'} explanation for ${part.text}${part.move.isPlayed ? ', player move' : ''}`}
          aria-expanded={selectedUci === part.move.uci} aria-controls={`${id}-move-detail`}
          onClick={() => onSelectCandidate(part.move!.uci)}>{part.text}</button>
      : part.text)}</p>),
  });
  const moveSpeech = useCoachSpeech({id: `${speechKey}:move:${selectedUci}`, reducedMotion,
    enabled: !!selectedMove && positionSpeech.complete, immediate: engineOnly,
    children: <>
      {selectedMove?.reason && <p className="candidate-reason">{moveExplanation(selectedMove.reason)}</p>}
      {selectedMove?.feedback && selectedMove.feedback !== selectedMove.reason && <p className="candidate-feedback">{moveExplanation(selectedMove.feedback)}</p>}
    </>,
  });
  const speaking = positionSpeech.speaking || moveSpeech.speaking;

  return <div className="coach-cards">
    <div className="coach-card-body" aria-busy={pending} ref={card} tabIndex={-1}>
      <div className={`coach-speech-controls${speaking ? ' is-speaking' : ''}`} aria-hidden={!speaking} inert={!speaking}>
        <div><button type="button" className="coach-show-all" aria-label="Show full coach explanation" onClick={() => {
          card.current?.focus({preventScroll: true}); positionSpeech.showAll(); moveSpeech.showAll();
        }}>Show all</button></div>
      </div>
      {(response?.coach_current === false || response?.classification_current === false) && <p className="coach-placeholder">This saved review uses an earlier coach.</p>}
      {response?.coach_current !== false && response?.classification_current !== false && response?.sharpness_current === false && <p className="coach-placeholder">This saved coaching uses earlier position labels.</p>}
      {teaching && !teaching.position_overview && <p className="coach-placeholder">This saved review has no practice summary.</p>}
      {!engineOnly && <>
      <section className="coach-section" aria-labelledby={`${id}-understand-title`}>
        <div className="coach-section-heading">
          <h3 id={`${id}-understand-title`}>Understand the position</h3>
        </div>
        {teaching ? <>
          {positionSpeech.content}
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
      {!inlineMoves && <section className="coach-section coach-moves-section" aria-labelledby={`${id}-moves-title`}>
        <div className="coach-section-heading moves-heading"><h3 id={`${id}-moves-title`}>Moves</h3></div>
        {rows.length ? <div className="candidate-moves" role="group" aria-label={`Candidate moves and ${playedLabel.toLowerCase()}`}>
          {rows.map(move => {
            const selected = selectedUci === move.uci;
            const score = move.engineMove ? engineEvaluation(scoreContext, move.engineMove) : null;
            return <div className={`candidate-row${move.isPlayed ? ' player-move-row' : ''}`} key={move.uci} data-uci={move.uci}>
              <button type="button" className="candidate-move" aria-label={`${selected ? 'Hide' : 'Show'} explanation for ${move.san}${move.isPlayed ? `, ${playedLabel.toLowerCase()}` : ''}`} aria-expanded={selected} aria-controls={`${id}-move-detail`} aria-pressed={selected} disabled={transitioning} onClick={() => onSelectCandidate(move.uci)}>
                <span className="candidate-heading">
                  <span className="move-labels"><strong>{move.san}</strong>
                    {move.isPlayed && <><span className="player-move-badge">{playedLabel}</span><span className={`move-quality ${quality}`} title={qualityDescription} aria-label={`${qualityLabel}. ${qualityDescription}`}>{acceptableQuality(quality) && <Check size={12} aria-hidden="true"/>}{qualityLabel}</span></>}
                  </span>
                  <span className="candidate-meta">
                    {score && <span id={`${id}-${move.uci}-score`} className={`engine-score ${score.tone}`} title={`${score.label} · ${score.perspective}'s perspective · depth ${move.engineMove?.depth}`} aria-label={`Evaluation ${score.value}, ${score.label}, ${score.perspective}'s perspective`}>{score.value}</span>}
                    <span className="move-board-action" title={selected ? 'Shown on board' : 'Show on board'}>{selected ? <Check size={15} aria-hidden="true"/> : <ArrowUpRight size={15} aria-hidden="true"/>}</span>
                  </span>
                </span>
              </button>
            </div>;
          })}
        </div> : <p className="coach-placeholder">{engineOnly ? reviewedMove ? 'No saved engine analysis for this move.' : 'No recorded move is selected.' : positionEvidence?.unclassified_reason === 'terminal_position' ? 'This position has ended.' : response ? 'No candidate moves are included in this saved response.' : 'Candidate moves and player feedback will appear here.'}</p>}
        {response && !response.played_move && <p className="move-empty-note">{moveFeedback?.explanation ?? (reviewedMove ? 'No saved feedback is available for the recorded move.' : 'No recorded move is available to evaluate.')}</p>}
      </section>}
      <div id={`${id}-move-detail`}>
        {selectedMove && positionSpeech.complete && (inlineMoves || selectedMove.reason || selectedMove.feedback || mistake) && <div key={selectedMove.uci} className={moveSpeech.speaking ? 'coach-move-reveal' : undefined}><div>
        <section className="move-detail" aria-label={`${selectedMove.san} explanation`}>
          {inlineMoves && <div className="candidate-heading">
            <h3>{selectedMove.san}{selectedMove.isPlayed && <>
              <span className="player-move-badge">{playedLabel}</span>
              <span className={`move-quality ${quality}`} title={qualityDescription} aria-label={`${qualityLabel}. ${qualityDescription}`}>{acceptableQuality(quality) && <Check size={12} aria-hidden="true"/>}{qualityLabel}</span>
            </>}</h3>
            {selectedScore && <span className={`engine-score ${selectedScore.tone}`} title={`${selectedScore.label} · ${selectedScore.perspective}'s perspective`}>{selectedScore.value}</span>}
          </div>}
          {moveSpeech.content}
          {mistake && moveSpeech.complete && <p className="mistake-classification">
            <span>Error classification:</span>
            <span className="mistake-category">{mistakeCategoryLabels[mistake.category]}</span>
            <span className="mistake-subcategory">{mistakeSubcategoryLabels[mistake.subcategory]}</span>
          </p>}
        </section></div></div>}
      </div>
    </div>
  </div>;
}
