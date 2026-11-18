import { fromMarkdown } from 'mdast-util-from-markdown';
import type { Nodes, RootContent } from 'mdast';
import type { EngineAnalysis, EngineMove } from './types.ts';

type Factor = { title: string; body: string };
type Section = 'position' | 'plan' | 'move';

function plain(node: Nodes): string {
  if ('value' in node) return node.value;
  return 'children' in node ? node.children.map(child => plain(child)).join('') : '';
}

function normalize(value: string): string {
  return value.toLowerCase().replace(/^\s*(?:\d+|[a-c])[.)]\s*/i, '').replace(/[:\s]+$/, '').trim();
}

// Only block headings and leading bold labels are structural. A phrase in the
// middle of a sentence must never split or remove a coach's explanation.
function label(node: RootContent): string {
  if (node.type === 'heading') return normalize(plain(node));
  if (node.type === 'paragraph' && node.children[0]?.type === 'strong') return normalize(plain(node.children[0]));
  return '';
}

export function parseCoachContent(markdown: string) {
  const source = (node: Nodes) => markdown.slice(node.position?.start.offset, node.position?.end.offset).trim();
  const afterLabel = (node: RootContent) => node.type === 'paragraph' && node.children[0]?.type === 'strong'
    ? markdown.slice(node.children[0].position?.end.offset, node.position?.end.offset).replace(/^\s*:\s*/, '').trim()
    : '';
  const sections: Record<Section, RootContent[]> = { position: [], plan: [], move: [] };
  let section: Section = 'position';
  for (const node of fromMarkdown(markdown).children) {
    const title = label(node);
    const next = title === 'understand the position' ? 'position' : title === 'develop a plan' ? 'plan' : title === 'evaluate your move' ? 'move' : null;
    if (next) section = next;
    else sections[section].push(node);
  }

  const factors: Factor[] = [];
  const intro: string[] = [];
  const thesis: string[] = [];
  let inThesis = false;
  function addFactor(nodes: RootContent[]) {
    const first = nodes[0];
    if (!first) return;
    const heading = first.type === 'heading' ? plain(first) : first.type === 'paragraph' && first.children[0]?.type === 'strong' ? plain(first.children[0]) : '';
    factors.push({
      title: heading.replace(/[:\s]+$/, '') || `Factor ${factors.length + 1}`,
      body: [heading ? afterLabel(first) : source(first), ...nodes.slice(1).map(source)].filter(Boolean).join('\n\n'),
    });
  }
  for (const node of sections.position) {
    const title = label(node);
    if (title === 'positional thesis') {
      inThesis = true;
      if (afterLabel(node)) thesis.push(afterLabel(node));
    } else if (inThesis) thesis.push(source(node));
    else if (['key positional factors', 'ranked positional factors', 'key factors'].includes(title)) continue;
    else if (node.type === 'list') node.children.forEach(item => addFactor(item.children));
    else if (/^(king safety|pawn structure|piece activity|space and square control|material and imbalances|tactical and dynamic factors)$/.test(title)) addFactor([node]);
    else if (factors.length) factors[factors.length - 1].body += '\n\n' + source(node);
    else intro.push(source(node));
  }

  const plan: Record<'intro' | 'objective' | 'approach' | 'moves', string[]> = { intro: [], objective: [], approach: [], moves: [] };
  let part: keyof typeof plan = 'intro';
  for (const node of sections.plan) {
    const title = label(node);
    const next = ['strategic objective', 'identify the objective'].includes(title) ? 'objective'
      : ['how to approach the position', 'explain the chess reasoning'].includes(title) ? 'approach'
        : ['moves to look for', 'candidate moves', 'find candidate moves'].includes(title) ? 'moves' : null;
    if (next) {
      part = next;
      if (afterLabel(node)) plan[part].push(afterLabel(node));
    } else plan[part].push(source(node));
  }
  return {
    factors, positionIntro: intro.join('\n\n'), thesis: thesis.join('\n\n'),
    planIntro: plan.intro.join('\n\n'), objective: plan.objective.join('\n\n'), approach: plan.approach.join('\n\n'),
    evaluation: sections.move.map(source).join('\n\n'),
  };
}

export function engineEvaluation(engine?: (Pick<EngineAnalysis, 'perspective'> & Partial<Pick<EngineAnalysis, 'played_move'>>) | null, move: EngineMove | undefined = engine?.played_move) {
  const score = move?.score;
  if (!engine || !score || !['White', 'Black'].includes(engine.perspective)) return null;
  const mate = typeof score.mate === 'number' && Number.isFinite(score.mate) ? score.mate : null;
  const cp = typeof score.cp === 'number' && Number.isFinite(score.cp) ? score.cp : null;
  if (mate === null && cp === null) return null;
  const bounded = score.bound === 'lower' || score.bound === 'upper';
  const sign = mate !== null ? (mate > 0 ? 1 : -1) : Math.sign(cp!);
  const winner = sign > 0 ? engine.perspective : engine.perspective === 'White' ? 'Black' : 'White';
  const level = mate === null && Math.abs(cp!) <= 20;
  const tone = bounded || level ? 'neutral' : sign > 0 ? 'favourable' : 'unfavourable';
  const value = mate !== null ? `${mate > 0 ? '+' : '−'}M${Math.abs(mate)}` : `${cp! > 0 ? '+' : cp! < 0 ? '−' : ''}${(Math.abs(cp!) / 100).toFixed(2)}`;
  const label = bounded ? `${score.bound === 'lower' ? 'Lower' : 'Upper'} bound`
    : mate !== null ? (mate === 0 ? `${engine.perspective} is checkmated` : `${winner} has mate in ${Math.abs(mate)}`)
      : level ? 'Approximately level' : `Favours ${winner}`;
  return { value: `${score.bound === 'lower' ? '≥ ' : score.bound === 'upper' ? '≤ ' : ''}${value}`, tone, label, perspective: engine.perspective };
}
