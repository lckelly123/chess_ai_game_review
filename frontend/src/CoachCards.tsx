import { useId, useMemo, useRef } from 'react';
import Markdown from 'react-markdown';
import { ArrowUpRight, Check, ChevronDown } from 'lucide-react';
import type { CoachResponse, Move } from './types';
import { engineEvaluation, parseCoachContent } from './coachContent';

function Prose({ children }: { children: string }) {
  return <div className="coach-prose"><Markdown skipHtml disallowedElements={['img']} components={{ h1: 'h4', h2: 'h4', h3: 'h4' }}>{children}</Markdown></div>;
}

const characterDescriptions = {
  quiet: 'Improve the position and coordinate your pieces.',
  tense: 'Watch threats, pawn tension, and move order.',
  forcing: 'Calculate immediate threats and forcing moves first.',
};

export type CoachTab = 'position' | 'move';
const tabs: { value: CoachTab; label: string }[] = [
  { value: 'position', label: 'Position & plan' },
  { value: 'move', label: 'Evaluate your move' },
];

export default function CoachCards({ response, nextMove, pending, selectedUci, onSelectCandidate, transitioning, activeTab, onTabChange }: {
  response?: CoachResponse; nextMove?: Move; pending: boolean;
  selectedUci?: string; onSelectCandidate: (uci: string) => void; transitioning: boolean;
  activeTab: CoachTab; onTabChange: (tab: CoachTab) => void;
}) {
  const id = useId();
  const tabButtons = useRef<(HTMLButtonElement | null)[]>([]);
  const content = useMemo(() => parseCoachContent(response?.text ?? ''), [response?.text]);
  const engine = response?.stockfish;
  const teaching = response?.teaching;
  const evaluation = engineEvaluation(engine);
  const topMoves = engine?.top_moves?.slice(0, 5) ?? [];
  const waiting = pending ? 'Your coach is thinking…' : 'Run coach to explore this position.';

  return <div className="coach-cards">
    <div className="coach-tabs" role="tablist" aria-label="Coach response sections">
      {tabs.map((tab, index) => <button
        key={tab.value} type="button" role="tab" id={`${id}-${tab.value}-tab`}
        aria-controls={`${id}-${tab.value}-panel`} aria-selected={activeTab === tab.value}
        tabIndex={activeTab === tab.value ? 0 : -1}
        ref={element => { tabButtons.current[index] = element; }}
        onClick={() => onTabChange(tab.value)}
        onKeyDown={event => {
          let next: number;
          if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
          else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
          else if (event.key === 'Home') next = 0;
          else if (event.key === 'End') next = tabs.length - 1;
          else return;
          event.preventDefault();
          onTabChange(tabs[next].value);
          tabButtons.current[next]?.focus();
        }}
      >{tab.label}</button>)}
    </div>
    <div className="coach-tabpanel" role="tabpanel" id={`${id}-position-panel`} aria-labelledby={`${id}-position-tab`} hidden={activeTab !== 'position'} tabIndex={0} aria-busy={pending}>
      <section className="coach-section" aria-labelledby={`${id}-understand-title`}>
        <h3 id={`${id}-understand-title`}>Understand the position</h3>
        {teaching ? <>
          <p className="position-character"><strong>{teaching.position_character}</strong><span>{teaching.candidate_moves.length ? characterDescriptions[teaching.position_character] : 'No legal moves remain.'}</span></p>
          <p className="teaching-paragraph">{teaching.positional_thesis}</p>
        </> : response ? <>
          {!!content.positionIntro && <Prose>{content.positionIntro}</Prose>}
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
        </> : <p className="coach-placeholder">{waiting} Its character and positional thesis will appear here.</p>}
      </section>
      <section className="coach-section" aria-labelledby={`${id}-plan-title`}>
        <h3 id={`${id}-plan-title`}>{teaching ? 'Needs of the position' : 'Develop a plan'}</h3>
        {teaching ? <>
          <div className="coach-subsection"><p className="teaching-paragraph">{teaching.needs_of_position}</p></div>
          <div className="coach-subsection candidate-section">
            <h4>Candidate moves</h4>
            {teaching.candidate_moves.length ? <>
              <p className="candidate-hint">Select a move to see its idea on the board.</p>
              <div className="candidate-moves" role="group" aria-label="Instructional candidate moves">
                {teaching.candidate_moves.map(candidate => {
                  const selected = selectedUci === candidate.uci;
                  return <button type="button" className="candidate-move" key={candidate.uci} aria-pressed={selected} disabled={transitioning} onClick={() => onSelectCandidate(candidate.uci)}>
                    <span className="candidate-heading"><strong>{response?.candidate_san?.[candidate.uci] ?? candidate.uci}</strong><span>{selected ? 'Shown on board' : 'Show on board'}{selected ? <Check size={15} aria-hidden="true"/> : <ArrowUpRight size={15} aria-hidden="true"/>}</span></span>
                    <span className="candidate-reason">{candidate.reason}</span>
                  </button>;
                })}
              </div>
              <p className="candidate-note">Coach suggestions · compare with the engine review.</p>
            </> : <p className="coach-placeholder">No legal moves are available in this position.</p>}
          </div>
        </> : <>
        {content.planIntro && <Prose>{content.planIntro}</Prose>}
        {content.objective && <div className="coach-subsection"><h4>Strategic objective</h4><Prose>{content.objective}</Prose></div>}
        {content.approach && <div className="coach-subsection"><h4>How to approach the position</h4><Prose>{content.approach}</Prose></div>}
        {!content.planIntro && !content.objective && !content.approach && <p className="coach-placeholder">{response ? 'No plan is included in this saved response.' : 'The needs of the position and candidate moves will appear here.'}</p>}
        </>}
      </section>
    </div>
    <div className="coach-tabpanel" role="tabpanel" id={`${id}-move-panel`} aria-labelledby={`${id}-move-tab`} hidden={activeTab !== 'move'} tabIndex={0} aria-busy={pending}>
      <h3 className="coach-section-title">Evaluate your move</h3>
      {evaluation && engine && <div className="engine-evaluation">
        <div className="engine-evaluation-heading">
          <div className="engine-played-move"><span>Your move</span><strong>{engine.played_move.san}</strong></div>
          <strong className={`engine-score ${evaluation.tone}`} title={`${evaluation.label} · depth ${engine.played_move.depth}`}>{evaluation.value}</strong>
        </div>
        {topMoves.length > 0 ? <table className="engine-moves">
          <caption>{topMoves.length === 1 ? 'Top engine move' : `Top ${topMoves.length} engine moves`}</caption>
          <thead><tr><th scope="col">Rank</th><th scope="col">Move</th><th scope="col">Eval</th></tr></thead>
          <tbody>{topMoves.map((move, index) => {
            const score = engineEvaluation(engine, move);
            const isPlayed = move.uci === engine.played_move.uci;
            return <tr key={move.uci} className={isPlayed ? 'engine-move-played' : undefined}>
              <td>{move.rank ?? index + 1}</td>
              <th scope="row"><span>{move.san}</span>{isPlayed && <span className="engine-your-move">Your move</span>}</th>
              <td><span className={`engine-score ${score?.tone ?? 'neutral'}`} title={score ? `${score.label} · depth ${move.depth}` : 'No score available'}>{score?.value ?? 'Unavailable'}</span></td>
            </tr>;
          })}</tbody>
        </table> : <p className="engine-unavailable">No candidate moves are available for this saved response.</p>}
        <p className="engine-source">{engine.engine} · {evaluation.perspective}’s perspective<br/>Scores in pawns; M means mate</p>
      </div>}
      {content.evaluation ? <>
        <Prose>{content.evaluation}</Prose>
        {!evaluation && <p className="engine-unavailable">No engine score is available for this saved response.</p>}
      </> : <p className="coach-placeholder">{!nextMove ? 'Final position. There is no next move to evaluate.' : pending ? `The review of ${nextMove.san} will appear when the coach finishes.` : response ? `No move review is saved for ${nextMove.san}. Run coach to evaluate it.` : `Run coach to review ${nextMove.san} against the plan and Stockfish.`}</p>}
    </div>
  </div>;
}
