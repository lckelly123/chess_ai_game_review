import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ArrowRight, CircleAlert, LoaderCircle, RefreshCw } from 'lucide-react';
import { api, timeControl } from './types';
import { analyticsUpdatedEvent, combineAnalytics, contexts, groupedOutlook, motifs, phases, pieces,
  outlooks, ratePoints, refreshAnalytics, sharpness } from './analyticsData';
import type { AnalyticsData, AnalyticsSummary } from './analyticsData';
import './analytics.css';

type ChartRow = { label: string; values: (number | null)[]; detail?: string };
const colors = ['var(--accent)', 'var(--negative)', 'var(--positive)', 'var(--warning)'];
const number = (value: number) => value.toLocaleString(undefined, {maximumFractionDigits: 1});
const titleCase = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

function Chart({title, rows, series, percent = false, note}: {
  title: string; rows: ChartRow[]; series: string[]; percent?: boolean; note?: string;
}) {
  const id = useId();
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(500);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, entry.contentRect.width)));
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const maximum = Math.max(0, ...rows.flatMap(row => row.values.map(value => value ?? 0)));
  const roughStep = Math.max(1, maximum / 4);
  const magnitude = 10 ** Math.floor(Math.log10(roughStep));
  const step = [1, 2, 5, 10].find(value => value * magnitude >= roughStep)! * magnitude;
  const top = percent ? 100 : step * 4;
  const tickCount = 4;
  const left = 44, right = 12, plotTop = 28, plotBottom = 208;
  const groupWidth = (width - left - right) / rows.length;
  const barWidth = Math.min(44, groupWidth * .72 / series.length);
  const angled = width < 420 && rows.length > 3;
  const height = angled ? 292 : 270;
  const unit = percent ? '%' : '';
  return <figure className="analytics-chart" aria-labelledby={`${id}-title`}>
    <figcaption id={`${id}-title`}><h3>{title}</h3></figcaption>
    <div className="analytics-chart-meta"><span>{percent ? 'Error rate (%)' : title.includes('Tactical') ? 'Number of errors' : 'Number of positional errors'}</span>
      {series.length > 1 && <div className="analytics-legend">{series.map((name, index) => <span key={name}><i style={{background: colors[index]}}/>{name}</span>)}</div>}
    </div>
    <div ref={container} className="analytics-plot">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby={`${id}-title ${id}-description`}>
        <desc id={`${id}-description`}>{rows.map(row => `${row.label}: ${row.values.map((value, i) => `${series[i]} ${value === null ? 'no data' : number(value) + unit}`).join(', ')}${row.detail ? ` (${row.detail})` : ''}`).join('. ')}</desc>
        {Array.from({length: tickCount + 1}, (_, i) => {
          const value = top * i / tickCount, y = plotBottom - value / top * (plotBottom - plotTop);
          return <g key={i}><line x1={left} x2={width - right} y1={y} y2={y} className="analytics-gridline"/>
            <text x={left - 9} y={y + 4} textAnchor="end" className="analytics-tick">{number(value)}{unit}</text></g>;
        })}
        {rows.map((row, rowIndex) => {
          const middle = left + groupWidth * (rowIndex + .5);
          return <g key={row.label}>
            {row.values.map((value, seriesIndex) => {
              const x = middle - barWidth * series.length / 2 + seriesIndex * barWidth + 2;
              const barHeight = (value ?? 0) / top * (plotBottom - plotTop);
              return <g key={seriesIndex}>
                {value !== null && <rect x={x} y={plotBottom - barHeight} width={Math.max(1, barWidth - 4)} height={barHeight}
                  fill={colors[seriesIndex]}><title>{row.label} · {series[seriesIndex]}: {number(value)}{unit}{row.detail ? ` · ${row.detail}` : ''}</title></rect>}
                {series.length === 1 && <text x={middle} y={plotBottom - barHeight - 8} textAnchor="middle" className="analytics-value">{value === null ? '—' : number(value) + unit}</text>}
              </g>;
            })}
            <text x={middle} y={plotBottom + 20} textAnchor={angled ? 'end' : 'middle'} className="analytics-tick"
              transform={angled ? `rotate(-35 ${middle} ${plotBottom + 20})` : undefined}>
              {!angled && row.label.includes(' ') ? row.label.split(' ').map((word, i) => <tspan key={i} x={middle} dy={i ? 14 : 0}>{word}</tspan>) : row.label}
            </text>
          </g>;
        })}
      </svg>
    </div>
    {note && <p className="analytics-chart-note">{note}</p>}
    <details className="analytics-data"><summary>View data</summary><div className="analytics-table-scroll" tabIndex={0} role="region" aria-label={`${title} data`}>
      <table><caption className="visually-hidden">{title}</caption><thead><tr><th scope="col">Category</th>{series.map(name => <th key={name} scope="col">{name}</th>)}{percent && <th scope="col">Sample</th>}</tr></thead>
        <tbody>{rows.map(row => <tr key={row.label}><th scope="row">{row.label}</th>{row.values.map((value, i) => <td key={i}>{value === null ? 'No data' : number(value) + unit}</td>)}{percent && <td>{row.detail}</td>}</tr>)}</tbody>
      </table></div></details>
  </figure>;
}

function PieceHeatmap({counts}: {counts: Record<string, Record<string, number>>}) {
  const maximum = Math.max(0, ...pieces.flatMap(piece => pieces.map(other => counts[piece][other])));
  return <figure className="analytics-chart analytics-heatmap"><figcaption><h3>Piece moved vs. engine’s top choice</h3></figcaption>
    <p className="analytics-chart-meta">Number of positional errors · engine’s choice across columns</p>
    <div className="analytics-table-scroll" tabIndex={0} role="region" aria-label="Piece comparison heatmap">
      <table><caption className="visually-hidden">Rows: piece actually moved. Columns: piece in the engine’s top choice. Cell values: positional errors.</caption>
        <thead><tr><th scope="col">Moved ↓</th>{pieces.map(piece => <th scope="col" key={piece}>{titleCase(piece)}</th>)}</tr></thead>
        <tbody>{pieces.map(piece => <tr key={piece}><th scope="row">{titleCase(piece)}</th>{pieces.map(other => {
          const count = counts[piece][other], intensity = maximum ? count / maximum : 0;
          return <td key={other} style={{backgroundColor: `color-mix(in srgb, var(--accent) ${intensity * 60}%, var(--surface))`}}
            title={`${titleCase(piece)} moved, ${other} preferred: ${count} positional errors`}>{number(count)}</td>;
        })}</tr>)}</tbody>
      </table>
    </div><p className="analytics-chart-note">Brighter cells mean more errors. Pieces are identified before the move.</p>
  </figure>;
}

function Section({title, description, children}: {title: string; description: string; children: ReactNode}) {
  return <section className="analytics-section" aria-label={title}><div className="analytics-section-heading"><h2>{title}</h2><p>{description}</p></div>{children}</section>;
}

function Graphs({data}: {data: AnalyticsSummary}) {
  const count = contexts.map(label => ({label, values: [data.decision_context[`${label.toLowerCase()}_count`] ?? 0]}));
  const rates = (name: 'phase' | 'sharpness' | 'outlook', categories: readonly string[]) => ratePoints(data[name], categories).map(point => ({
    label: point.label, values: [point.rate], detail: `${number(point.errors)} errors / ${number(point.moves)} moves`,
  }));
  return <>
    <Section title="Tactical" description="Coach-reviewed errors">
      <Chart title="Tactical error distribution" series={['Tactical missed', 'Tactical allowed']}
        rows={motifs.map((motif, index) => ({label: ['Hanging piece', 'Fork', 'Pin/skewer', 'Discovered attack'][index],
          values: [data.tactical[`${motif}_missed`] ?? 0, data.tactical[`${motif}_allowed`] ?? 0]}))}/>
    </Section>
    <Section title="Positional" description="Coach-reviewed errors">
      <div className="analytics-pair"><Chart title="Decision context distribution" series={['Errors']} rows={count}/>
        <PieceHeatmap counts={data.piece_comparison.counts}/></div>
      <Chart title="Decision context × position outlook" series={[...contexts]} rows={groupedOutlook(data.context_outlook.counts)}
        note="Losing includes Worse; Winning includes Better. Outlook is measured before your move."/>
    </Section>
    <Section title="Game Stats" description="All reliably graded player moves">
      <p className="analytics-explanation">Error rate = inaccuracies, mistakes, and blunders ÷ graded moves. Uncertain grades are excluded; — means no eligible moves.</p>
      <div className="analytics-pair"><Chart title="Error rate by game phase" rows={rates('phase', phases)} series={['Error rate']} percent/>
        <Chart title="Error rate by position sharpness" rows={rates('sharpness', sharpness)} series={['Error rate']} percent note="Positions without a sharpness classification are excluded."/></div>
      <Chart title="Error rate by position outlook" rows={rates('outlook', outlooks)} series={['Error rate']} percent
        note="From your perspective, before the move: Losing < −3; Worse −3 to < −0.5; Equal −0.5 to +0.5; Better > +0.5 to +3; Winning > +3 pawns. Forced mates are Losing or Winning."/>
    </Section>
  </>;
}

export default function Analytics({username, profilesLoading, profileError, onRetryProfiles}: {
  username: string; profilesLoading: boolean; profileError: string; onRetryProfiles: () => void;
}) {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(!!username);
  const [revision, setRevision] = useState(0);
  const [speed, setSpeed] = useState('all');
  const [control, setControl] = useState('all');
  useEffect(() => {
    if (!username) { setLoading(false); return; }
    let live = true;
    setLoading(true); setError('');
    void refreshAnalytics(username).then(result => { if (live) setData(result); })
      .catch(err => { if (live) setError(err instanceof Error ? err.message : 'Could not refresh analytics.'); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [username, revision]);
  useEffect(() => {
    const receive = (event: Event) => {
      const next = (event as CustomEvent<AnalyticsData>).detail;
      if (next.username === username) { setData(next); setError(''); }
    };
    // Saved summaries change as background analysis finishes; these reads never
    // start analysis or rebuild data. Pause polling while this tab is hidden.
    let live = true;
    const read = () => { if (username && !document.hidden) void api<AnalyticsData>(`/api/analytics?username=${encodeURIComponent(username)}`)
      .then(next => { if (live) setData(next); }).catch(() => { /* Keep the last successful snapshot; explicit refresh reports errors. */ }); };
    const timer = window.setInterval(read, 10000);
    window.addEventListener(analyticsUpdatedEvent, receive);
    document.addEventListener('visibilitychange', read);
    return () => { live = false; window.clearInterval(timer); window.removeEventListener(analyticsUpdatedEvent, receive); document.removeEventListener('visibilitychange', read); };
  }, [username]);
  const available = data?.time_controls ?? [];
  const speeds = [...new Set(available.map(row => row.time_class))];
  const effectiveSpeed = speed === 'all' || speeds.includes(speed) ? speed : 'all';
  const controls = [...new Set(available.filter(row => effectiveSpeed === 'all' || row.time_class === effectiveSpeed).map(row => row.time_control_raw))];
  const effectiveControl = control === 'all' || controls.includes(control) ? control : 'all';
  const summary = useMemo(() => combineAnalytics(available.filter(row => (effectiveSpeed === 'all' || row.time_class === effectiveSpeed)
    && (effectiveControl === 'all' || row.time_control_raw === effectiveControl))), [data, effectiveSpeed, effectiveControl]);
  const graded = phases.reduce((sum, phase) => sum + (summary.phase[`${phase.toLowerCase()}_moves`] ?? 0), 0);
  return <div className="analytics">
    <div className="library-heading"><div><h1>Analytics</h1><p>See where your decisions go wrong, across your games.</p></div>
      {username && <button className="secondary-button" disabled={loading || profilesLoading} onClick={() => setRevision(value => value + 1)}><RefreshCw size={15} className={loading ? 'spin' : ''}/>Refresh</button>}
    </div>
    {(error || profileError) && <div className="sync-notice" role="alert"><CircleAlert size={18}/><div><p>{profileError || error}</p>
      {data && <p>Showing the last loaded summary.</p>}<button className="text-button" onClick={() => profileError ? onRetryProfiles() : setRevision(value => value + 1)}>Try again</button></div></div>}
    {!username && !profilesLoading ? <div className="library-empty"><h2>Your decisions, in perspective</h2><p>Add or select an account above to see its analytics.</p></div>
      : (loading || profilesLoading) && !data ? <div className="library-empty" role="status"><LoaderCircle className="spin" size={24}/><p>Loading analytics…</p></div>
      : data && <>
        <div className="analytics-toolbar"><div className="analytics-filters">
          <label>Speed<select aria-label="Speed" value={effectiveSpeed} onChange={event => { setSpeed(event.target.value); setControl('all'); }}><option value="all">All speeds</option>{speeds.map(value => <option key={value} value={value}>{titleCase(value)}</option>)}</select></label>
          <label>Time control<select aria-label="Time control" value={effectiveControl} onChange={event => setControl(event.target.value)}><option value="all">All controls</option>{controls.map(value => <option key={value} value={value}>{value ? timeControl(value) : 'Unknown'}</option>)}</select></label>
        </div><p role="status" aria-live="polite">{number(graded)} graded moves{data.updated_at && <span>Updated {new Date(data.updated_at).toLocaleTimeString(undefined, {hour: 'numeric', minute: '2-digit'})}</span>}</p></div>
        {!graded && <div className="analytics-empty"><p>No graded moves for this selection yet. Analyze a game to fill these graphs.</p><a className="back-link" href="#games">Go to your games <ArrowRight size={15}/></a></div>}
        <Graphs data={summary}/>
      </>}
  </div>;
}
