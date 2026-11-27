import { useEffect, useState } from 'react';
import { BOARD_MOVE_MS, movePreviewSteps } from './boardAnimation';
import type { MovePreviewStep } from './boardAnimation';
import type { Position } from './types';

type Preview = {key: string; uci: string; steps: MovePreviewStep[]; index: number};

export function useMovePreview(key: string, reducedMotion: boolean) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const current = preview?.key === key ? preview : null;
  useEffect(() => { setPreview(null); }, [key]);
  useEffect(() => {
    if (!current || current.index === current.steps.length - 1) return;
    const timer = window.setTimeout(() => {
      setPreview(value => value === current ? {...value, index: value.index + 1} : value);
    }, reducedMotion ? 120 : BOARD_MOVE_MS + 80);
    return () => window.clearTimeout(timer);
  }, [current, reducedMotion]);

  return {
    frame: current?.steps[current.index],
    reverting: !!current && current.index < current.steps.length - 1,
    uci: current?.uci,
    clear: () => setPreview(null),
    play: (decision: Position, shown: Position, destination: Position, uci: string, undoUci?: string) => {
      setPreview({key, uci, steps: movePreviewSteps(decision, shown, destination, uci, undoUci), index: 0});
    },
  };
}
