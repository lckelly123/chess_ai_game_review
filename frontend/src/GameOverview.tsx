import { useId, useMemo } from 'react';
import type { CoachResponse, EngineReview, GameDetail, GameStatistics, PositionEvaluation } from './types';
import { engineEvaluation } from './coachContent';
import { matchingReview, qualityLabels } from './engineReview';
import { positionDecision } from './positionDecision';
import { evaluationLabel, evaluationPercent, moveTime, overviewCounts, overviewTimeline, statisticsReady, summaryGrades } from './overviewData';
import './gameOverview.css';

function EvaluationGraph({ timeline, game, reviews, ply, onSelect }: {
  timeline: PositionEvaluation[]; game: GameDetail; reviews: Record<string, EngineReview>; ply: number; onSelect: (ply: number) => void;
}) {
  const id = useId();
  const width = 260, height = 104, padding = 8;
  const x = (index: number) => padding + index / Math.max(1, timeline.length - 1) * (width - padding * 2);
  const y = (point: PositionEvaluation) => {
    const percent = evaluationPercent(point);
    return percent == null ? null : padding + (100 - percent) / 100 * (height - padding * 2);
  };
  const segments: {x: number; y: number}[][] = [];
  let segment: {x: number; y: number}[] = [];
  timeline.forEach((point, index) => {
    const value = y(point);
    if (value == null) { if (segment.length) segments.push(segment); segment = []; }
    else segment.push({x: x(index), y: value});
  });
  if (segment.length) segments.push(segment);
  const currentY = timeline[ply] ? y(timeline[ply]) : null;
  const currentLabel = ply === 0 ? 'Starting position' : `After ${game.moves[ply - 1]?.san}`;
  return <section className="overview-evaluation" aria-label="Game evaluation">
    <div className="overview-section-heading"><h2>Evaluation</h2><span title="Positive favours White; negative favours Black">{evaluationLabel(timeline[ply])}</span></div>
    <div className="overview-chart">
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
        <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#ad89ef" stopOpacity=".5"/><stop offset="100%" stopColor="#ad89ef" stopOpacity=".12"/></linearGradient></defs>
        <line x1={padding} x2={width - padding} y1={height / 2} y2={height / 2} className="evaluation-baseline"/>
        {segments.map((points, index) => {
          const path = points.map((point, i) => `${i ? 'L' : 'M'}${point.x},${point.y}`).join(' ');
          return <g key={index}><path d={`${path} L${points.at(-1)!.x},${height / 2} L${points[0].x},${height / 2} Z`} fill={`url(#${id})`}/><path d={path} className="evaluation-line"/></g>;
        })}
        {game.moves.map((move, index) => {
          const grade = matchingReview(move, game.positions[index], reviews[String(index)])?.stockfish.move_quality?.status;
          const value = y(timeline[index + 1]);
          return grade && grade !== 'good' && grade !== 'uncertain' && value != null
            ? <circle key={index} cx={x(index + 1)} cy={value} r="2.8" className={`evaluation-event ${grade}`}/> : null;
        })}
        <line x1={x(ply)} x2={x(ply)} y1={padding} y2={height - padding} className="evaluation-cursor"/>
        {currentY != null && <circle cx={x(ply)} cy={currentY} r="4" className="evaluation-current"/>}
      </svg>
      {!segments.length && <span className="evaluation-empty">No evaluations yet</span>}
      <input type="range" min={0} max={Math.max(0, timeline.length - 1)} value={ply} onChange={event => onSelect(Number(event.target.value))}
        aria-label="Browse evaluation graph" aria-valuetext={`${currentLabel}: ${evaluationLabel(timeline[ply])}, White’s perspective`}/>
    </div>
    <div className="evaluation-axis" aria-hidden="true"><span>Start</span><span>White ↑ · Black ↓</span><span>{game.moves.at(-1)?.number ?? 0}</span></div>
  </section>;
}

export default function GameOverview({ game, reviews, statistics, ply, onSelect, response, onMainLine, analyzing, submitting, onComplete }: {
  game: GameDetail; reviews: Record<string, EngineReview>; statistics?: GameStatistics | null; ply: number; onSelect: (ply: number) => void;
  response?: CoachResponse; onMainLine: boolean; analyzing: boolean; submitting: boolean; onComplete: () => void;
}) {
  const timeline = useMemo(() => overviewTimeline(game, reviews, statistics), [game, reviews, statistics]);
  const counts = useMemo(() => overviewCounts(game, reviews), [game, reviews]);
  const move = onMainLine ? game.moves[ply - 1] : undefined;
  const review = onMainLine ? matchingReview(move, game.positions[ply - 1], reviews[String(ply - 1)]) : undefined;
  const currentReview = matchingReview(game.moves[ply], game.positions[ply], reviews[String(ply)]);
  const evidence = onMainLine ? currentReview?.position_evidence
    ?? (response?.fen === game.positions[ply].fen ? response?.position_evidence : undefined) ?? timeline[ply]?.position_evidence : undefined;
  const decision = positionDecision(evidence);
  const sharpness = !decision || decision.className === 'unclassified' ? null : evidence?.sharpness?.score;
  const score = review ? engineEvaluation(review.stockfish, review.stockfish.played_move, 'White') : null;
  const quality = review?.stockfish.move_quality?.status;
  const ready = statisticsReady(game, statistics);
  const analysed = counts.white.analysed + counts.black.analysed;
  const uncertain = counts.white.uncertain + counts.black.uncertain;
  const phase = onMainLine ? game.positions[ply].phase : undefined;
  return <aside className="game-overview" aria-label="Game overview">
    <EvaluationGraph timeline={timeline} game={game} reviews={reviews} ply={ply} onSelect={onSelect}/>
    <section className="overview-summary" aria-label="Overall game summary">
      <div className="overview-players">{(['white', 'black'] as const).map(color => <div className="overview-player" key={color}>
        <span className="overview-color"><span className={`color-token ${color}`}/>{color === 'white' ? 'White' : 'Black'}</span>
        <strong title={game[color]}>{game[color]}</strong>
      </div>)}</div>
      <table className="overview-stats"><caption className="visually-hidden">Whole-game statistics, White on the left and Black on the right</caption>
        <thead className="visually-hidden"><tr><th scope="col">White</th><th scope="col">Statistic</th><th scope="col">Black</th></tr></thead>
        <tbody><tr className="overview-accuracy"><td>{ready && statistics.accuracy.white != null ? `${statistics.accuracy.white.toFixed(1)}%` : '—'}</td><th scope="row">Accuracy</th><td>{ready && statistics.accuracy.black != null ? `${statistics.accuracy.black.toFixed(1)}%` : '—'}</td></tr>
          {summaryGrades.map(grade => <tr key={grade} className={`overview-grade ${grade}`}><td>{counts.white.analysed ? counts.white[grade] : '—'}</td><th scope="row"><span className="grade-dot"/>{qualityLabels[grade]}</th><td>{counts.black.analysed ? counts.black[grade] : '—'}</td></tr>)}
        </tbody>
      </table>
      {(!ready || uncertain > 0) && <p className="overview-status" role="status">{analyzing ? `Analysing ${analysed}/${game.moves.length} moves…` : !ready ? <button className="text-button" type="button" disabled={submitting} onClick={onComplete}>{submitting ? 'Starting…' : analysed ? 'Complete game statistics' : 'Analyse game'}</button> : null}{uncertain > 0 && <span>{uncertain} ungraded {uncertain === 1 ? 'move' : 'moves'}</span>}</p>}
    </section>
    <section className="overview-position" aria-label="Current position and recorded move">
      <div className="overview-section-heading"><h2>Position sharpness</h2><span>{phase ? {opening: 'Opening', middlegame: 'Middlegame', endgame: 'Endgame'}[phase] : '—'}</span></div>
      <div className="overview-sharpness" title={decision?.tooltip}>
        <span className={`decision-tag ${decision?.className ?? 'unclassified'}`} tabIndex={0} aria-label={decision ? `${decision.label}: ${decision.tooltip}` : undefined}>{decision?.label ?? (onMainLine ? timeline[ply]?.status === 'terminal' ? 'Game over' : 'Not analysed' : 'Variation')}</span>
        <span className="sharpness-value">{sharpness == null ? '—' : sharpness.toFixed(0)}<small> / 100</small></span>
      </div>
      <div className="overview-move"><span>Played</span><div className="overview-played-move"><strong>{move ? `${move.number}${move.color === 'white' ? '.' : '…'} ${move.san}` : onMainLine ? 'Starting position' : 'Exploring variation'}</strong>{quality && <span className={`move-quality ${quality}`}>{qualityLabels[quality]}</span>}</div></div>
      <dl className="overview-move-data"><div><dt>Time taken</dt><dd title={move?.elapsed_seconds == null ? 'No recorded move timing available' : undefined}>{move ? moveTime(move.elapsed_seconds) : '—'}</dd></div>
        <div><dt>Move evaluation</dt><dd className={score?.tone ?? ''} title={score ? `${score.label} · depth ${review?.stockfish.played_move.depth}` : undefined}>{move ? score?.value ?? '—' : '—'}</dd></div></dl>
    </section>
  </aside>;
}
