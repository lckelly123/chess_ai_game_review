import { Children, Fragment, cloneElement, isValidElement, useEffect, useState, type ReactNode } from 'react';

const readPassages = new Set<string>();
const TICK_MS = 24;
const CHARACTERS_PER_TICK = 3;

export function resetCoachSpeech(gameIds: string[]) {
  const ids = new Set(gameIds);
  for (const key of readPassages) {
    if (ids.has(key.slice('coach-speech:v1:'.length).split(':')[0])) readPassages.delete(key);
  }
}

function textOf(children: ReactNode): string {
  return Children.toArray(children).map(child => {
    if (typeof child === 'string' || typeof child === 'number') return String(child);
    return isValidElement<{children?: ReactNode}>(child) ? textOf(child.props.children) : '';
  }).join('');
}

function passageKey(id: string, text: string) {
  let hash = 0;
  for (const character of text) hash = (Math.imul(hash, 31) + character.codePointAt(0)!) | 0;
  return `coach-speech:v1:${id}:${hash}`;
}

function wasRead(key: string) {
  if (readPassages.has(key)) return true;
  try { return localStorage.getItem(key) === 'read'; } catch { return false; }
}

function remember(key: string) {
  readPassages.add(key);
  try { localStorage.setItem(key, 'read'); } catch { /* Reading still works without storage. */ }
}

// Preserve the final line wrapping while revealing text. Screen readers receive
// each complete text node once; no character-by-character live announcements.
function reveal(children: ReactNode, count: number): ReactNode {
  let remaining = count;
  const visit = (nodes: ReactNode): ReactNode => Children.map(nodes, child => {
    if (typeof child === 'string' || typeof child === 'number') {
      const text = String(child);
      const visible = Math.max(0, Math.min(remaining, text.length));
      remaining -= text.length;
      if (visible === text.length) return child;
      return <Fragment><span className="visually-hidden">{text}</span><span aria-hidden="true">{text.slice(0, visible)}<span className="coach-unspoken">{text.slice(visible)}</span></span></Fragment>;
    }
    if (!isValidElement<{children?: ReactNode; className?: string; 'aria-hidden'?: boolean; inert?: boolean}>(child)) return child;
    // Move names and PV links are complete, usable units, never partial notation.
    if (child.type === 'button' || child.type === 'a') {
      remaining -= textOf(child.props.children).length;
      return remaining >= 0 ? child : <Fragment><span className="visually-hidden">{textOf(child.props.children)}</span>{cloneElement(child, {
        className: `${child.props.className ?? ''} coach-unspoken`, 'aria-hidden': true, inert: true,
      })}</Fragment>;
    }
    return cloneElement(child, {}, visit(child.props.children));
  });
  return visit(children);
}

export function useCoachSpeech({ id, children, enabled = true, immediate = false, reducedMotion = false }: {
  id: string; children: ReactNode; enabled?: boolean; immediate?: boolean; reducedMotion?: boolean;
}) {
  const text = textOf(children);
  const key = passageKey(id, text);
  const [progress, setProgress] = useState({key, count: 0});
  const complete = !text || immediate || reducedMotion || typeof window === 'undefined' || wasRead(key)
    || (progress.key === key && progress.count >= text.length);
  const count = complete ? text.length : progress.key === key ? progress.count : 0;

  useEffect(() => {
    if (!enabled || !text) return;
    if (complete) { remember(key); return; }
    let cursor = count;
    let timer: number;
    const tick = () => {
      // Background tabs resume at the same point instead of consuming the speech.
      if (document.hidden) { timer = window.setTimeout(tick, 200); return; }
      const next = Math.min(cursor + CHARACTERS_PER_TICK, text.length);
      const punctuation = /[.!?](?:\s|$)/.test(text.slice(cursor, next + 1));
      cursor = next;
      setProgress({key, count: cursor});
      if (cursor < text.length) timer = window.setTimeout(tick, punctuation ? 140 : TICK_MS);
    };
    timer = window.setTimeout(tick, TICK_MS);
    return () => window.clearTimeout(timer);
    // Progress ticks belong to this timer; a new passage cancels it completely.
  }, [key, enabled, complete, text]);

  return {
    complete, speaking: enabled && !complete,
    // Keep React's mapped keys stable at completion so focused move links survive.
    content: reveal(children, complete ? text.length : enabled ? count : 0),
    showAll: () => { remember(key); setProgress({key, count: text.length}); },
  };
}
