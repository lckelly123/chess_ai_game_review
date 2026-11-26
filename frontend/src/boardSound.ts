export type BoardSound = 'move' | 'capture';

export function boardMoveSound(previousFen: string, nextFen: string): BoardSound | null {
  const before = previousFen.split(' ')[0];
  const after = nextFen.split(' ')[0];
  if (before === after) return null;
  // Counting in either direction also covers undoing captures and en passant.
  const pieceCount = (placement: string) => placement.replace(/[^a-z]/gi, '').length;
  return pieceCount(before) === pieceCount(after) ? 'move' : 'capture';
}

// One player per mounted board. Fetch early, then unlock Web Audio in a user
// gesture so delayed practice responses and autoplay can also make sound.
export function createBoardSoundPlayer() {
  const files: Record<BoardSound, string> = {move: 'Move.mp3', capture: 'Capture.mp3'};
  const data = Object.fromEntries(Object.entries(files).map(([name, file]) => [name,
    fetch(`/assets/chess/sounds/${file}`).then(response => {
      if (!response.ok) throw new Error('Could not load board sound.');
      return response.arrayBuffer();
    }).catch(() => null),
  ])) as Record<BoardSound, Promise<ArrayBuffer | null>>;
  let context: AudioContext | undefined;
  const buffers: Partial<Record<BoardSound, Promise<AudioBuffer | null>>> = {};
  let source: AudioBufferSourceNode | undefined;
  let request = 0;
  let disposed = false;

  const unlock = () => {
    if (disposed) return;
    try {
      if (!context) {
        const audioContext = new AudioContext();
        context = audioContext;
        for (const name of Object.keys(files) as BoardSound[]) {
          buffers[name] = data[name].then(bytes => bytes && !disposed
            ? audioContext.decodeAudioData(bytes) : null).catch(() => null);
        }
      }
      void context.resume().catch(() => {});
    } catch { /* Audio support must never prevent a board move. */ }
  };
  document.addEventListener('pointerdown', unlock, true);
  document.addEventListener('keydown', unlock, true);

  return {
    async play(sound: BoardSound) {
      const currentRequest = ++request;
      if (!context || disposed) return;
      try {
        await context.resume();
        const buffer = await buffers[sound];
        // Loading or resuming audio must not queue up old moves during scrubbing.
        if (!buffer || disposed || currentRequest !== request || context.state !== 'running') return;
        source?.stop();
        source = context.createBufferSource();
        source.buffer = buffer;
        source.connect(context.destination);
        source.start();
      } catch { /* Blocked audio or missing assets leave navigation usable. */ }
    },
    dispose() {
      disposed = true;
      document.removeEventListener('pointerdown', unlock, true);
      document.removeEventListener('keydown', unlock, true);
      source?.stop();
      void context?.close().catch(() => {});
    },
  };
}
