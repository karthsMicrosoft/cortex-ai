import { useCallback, useEffect, useRef, useState } from 'react';
import { Pause, Play, Volume2 } from 'lucide-react';

// ---------------------------------------------------------------------------
// Music metadata type
// ---------------------------------------------------------------------------

export interface MusicMetadata {
  tempo?: number;       // BPM
  key?: string;         // e.g. "C major"
  genre?: string;       // e.g. "Jazz"
  mood?: string;        // e.g. "Melancholic"
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface MusicPlayerProps {
  audioUrl: string;
  metadata?: MusicMetadata;
  className?: string;
}

// ---------------------------------------------------------------------------
// Helpers — dynamic WaveSurfer import
// ---------------------------------------------------------------------------

type WaveSurferInstance = {
  play: () => void;
  pause: () => void;
  destroy: () => void;
  isPlaying: () => boolean;
  on: (event: string, cb: (...args: unknown[]) => void) => void;
  getDuration: () => number;
  getCurrentTime: () => number;
};

async function createWaveSurfer(
  container: HTMLDivElement,
  audioUrl: string,
): Promise<WaveSurferInstance> {
  // Dynamic import so wavesurfer.js is code-split and not bundled if unused
  const WaveSurfer = (await import('wavesurfer.js')).default;
  const ws = WaveSurfer.create({
    container,
    waveColor: '#6366F1',
    progressColor: '#4F46E5',
    cursorColor: '#a5b4fc',
    barWidth: 2,
    barRadius: 2,
    height: 56,
    normalize: true,
    url: audioUrl,
  }) as unknown as WaveSurferInstance;
  return ws;
}

function formatTime(seconds: number): string {
  if (!isFinite(seconds) || isNaN(seconds)) return '0:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

// ---------------------------------------------------------------------------
// MusicPlayer component
// ---------------------------------------------------------------------------

/**
 * MusicPlayer — wavesurfer.js v7.8 waveform player.
 *
 * Waveform colours:
 *   waveColor:    #6366F1  (indigo-500)
 *   progressColor: #4F46E5 (indigo-600)
 *
 * Props:
 *   audioUrl — URL to the audio file (SAS-signed blob URL)
 *   metadata  — optional { tempo, key, genre, mood } displayed as chips
 *
 * US-6 Task 6.1.
 */
export function MusicPlayer({ audioUrl, metadata, className = '' }: MusicPlayerProps): React.ReactElement {
  const containerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurferInstance | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isReady, setIsReady] = useState(false);
  const [wsError, setWsError] = useState<string | null>(null);

  // Initialise WaveSurfer
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let destroyed = false;
    let ws: WaveSurferInstance | null = null;

    void createWaveSurfer(container, audioUrl)
      .then((instance) => {
        if (destroyed) {
          instance.destroy();
          return;
        }
        ws = instance;
        wsRef.current = ws;

        ws.on('ready', () => {
          if (!destroyed) {
            setDuration(ws!.getDuration());
            setIsReady(true);
          }
        });

        ws.on('audioprocess', () => {
          if (!destroyed) {
            setCurrentTime(ws!.getCurrentTime());
          }
        });

        ws.on('play', () => {
          if (!destroyed) setIsPlaying(true);
        });

        ws.on('pause', () => {
          if (!destroyed) setIsPlaying(false);
        });

        ws.on('finish', () => {
          if (!destroyed) {
            setIsPlaying(false);
            setCurrentTime(0);
          }
        });

        ws.on('error', (err: unknown) => {
          if (!destroyed) {
            setWsError(err instanceof Error ? err.message : 'Audio load failed');
          }
        });
      })
      .catch((err: Error) => {
        if (!destroyed) setWsError(err.message);
      });

    return () => {
      destroyed = true;
      wsRef.current?.destroy();
      wsRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioUrl]);

  const handleTogglePlay = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || !isReady) return;
    if (ws.isPlaying()) {
      ws.pause();
    } else {
      ws.play();
    }
  }, [isReady]);

  // Metadata chips
  const chips: Array<{ label: string; value: string }> = [];
  if (metadata?.tempo) chips.push({ label: 'BPM', value: String(metadata.tempo) });
  if (metadata?.key) chips.push({ label: 'Key', value: metadata.key });
  if (metadata?.genre) chips.push({ label: 'Genre', value: metadata.genre });
  if (metadata?.mood) chips.push({ label: 'Mood', value: metadata.mood });

  return (
    <div
      className={[
        'flex flex-col gap-3 rounded-xl border border-slate-700 bg-slate-800/60 p-4',
        className,
      ].join(' ')}
      aria-label="Music player"
    >
      {/* Waveform container */}
      <div
        ref={containerRef}
        className="w-full overflow-hidden rounded-lg bg-slate-900"
        aria-label="Audio waveform"
      />

      {wsError && (
        <p className="text-xs text-red-400" role="alert">
          {wsError}
        </p>
      )}

      {/* Controls row */}
      <div className="flex items-center gap-3">
        {/* Play / Pause */}
        <button
          type="button"
          onClick={handleTogglePlay}
          disabled={!isReady}
          aria-label={isPlaying ? 'Pause' : 'Play'}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-white transition-colors hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPlaying ? (
            <Pause className="h-4 w-4" aria-hidden="true" />
          ) : (
            <Play className="h-4 w-4" aria-hidden="true" />
          )}
        </button>

        {/* Time display */}
        <div className="flex flex-1 items-center gap-1 text-xs tabular-nums text-slate-400">
          <Volume2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span aria-live="polite" aria-atomic="true">
            {formatTime(currentTime)}
          </span>
          <span className="text-slate-600">/</span>
          <span>{formatTime(duration)}</span>
        </div>
      </div>

      {/* Metadata chips */}
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5" aria-label="Music metadata">
          {chips.map(({ label, value }) => (
            <span
              key={label}
              className="rounded-full border border-purple-700 bg-purple-900/40 px-2 py-0.5 text-xs text-purple-300"
            >
              <span className="text-purple-500">{label}: </span>
              {value}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default MusicPlayer;
