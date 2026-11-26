import { useEffect, useRef } from 'react';
import { boardMoveSound, createBoardSoundPlayer } from './boardSound';

export function useBoardSound(fen: string) {
  const previousFen = useRef(fen);
  const player = useRef<ReturnType<typeof createBoardSoundPlayer> | null>(null);
  useEffect(() => {
    const audio = createBoardSoundPlayer();
    player.current = audio;
    return () => { player.current = null; audio.dispose(); };
  }, []);
  useEffect(() => {
    const sound = boardMoveSound(previousFen.current, fen);
    previousFen.current = fen;
    if (sound) void player.current?.play(sound);
  }, [fen]);
}
