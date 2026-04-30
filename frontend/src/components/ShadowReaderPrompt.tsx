/**
 * ShadowReaderPrompt — bottom-sheet component for the Shadow Reader feature (US-8).
 *
 * Behaviour:
 *  - Polls GET /api/notes/{noteId}/shadow-reader on the B17 tiered schedule:
 *      Phase 1: 10 polls × 2s intervals (0–20s)
 *      Phase 2:  5 polls × 5s intervals (20–45s)
 *    Stops immediately on any terminal status (asked | skipped | dismissed | answered).
 *  - Renders a fixed-bottom bottom-sheet when status === 'asked'.
 *  - Dismiss (X) → POST dismiss; Answer (Send) → POST answer.
 *  - Voice-mic button uses useVoiceRecorder; transcribed text is pasted into textarea.
 *  - Never blocks the UI — rendered via a fixed overlay, always has a dismiss button.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Mic, Send, Sparkles, X } from 'lucide-react';
import { answer, dismiss, getQuestions } from '../api/shadowReader';
import type { ShadowReaderStatus } from '../api/shadowReader';
import { useVoiceRecorder } from '../hooks/useVoiceRecorder';

// ---------------------------------------------------------------------------
// B17 polling schedule
// ---------------------------------------------------------------------------

/** Each entry is [intervalMs, maxPolls] */
const POLL_PHASES: [number, number][] = [
  [2000, 10], // Phase 1: 10 polls × 2s = 0–20s
  [5000, 5],  // Phase 2:  5 polls × 5s = 20–45s
];

const TERMINAL_STATUSES: ShadowReaderStatus[] = ['asked', 'skipped', 'dismissed', 'answered'];

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface Props {
  noteId: string;
  onComplete?: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type UiStatus = 'loading' | 'asked' | 'hidden';

export function ShadowReaderPrompt({ noteId, onComplete }: Props): React.ReactElement | null {
  const [uiStatus, setUiStatus] = useState<UiStatus>('loading');
  const [questions, setQuestions] = useState<string[]>([]);
  const [answerText, setAnswerText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Voice recording
  const recorder = useVoiceRecorder();
  const [isTranscribing, setIsTranscribing] = useState(false);

  // Polling refs
  const phaseRef = useRef(0);
  const pollCountRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // -----------------------------------------------------------------------
  // Polling logic
  // -----------------------------------------------------------------------

  const schedulePoll = useCallback(
    (onPoll: () => Promise<void>) => {
      const [intervalMs, maxPolls] = POLL_PHASES[phaseRef.current] ?? [0, 0];
      if (maxPolls === 0) {
        // All phases exhausted — give up
        setUiStatus('hidden');
        return;
      }

      timerRef.current = setTimeout(async () => {
        await onPoll();
        pollCountRef.current += 1;

        if (pollCountRef.current >= maxPolls) {
          // Advance to next phase
          phaseRef.current += 1;
          pollCountRef.current = 0;
        }
      }, intervalMs);
    },
    [],
  );

  useEffect(() => {
    if (!noteId) return;

    phaseRef.current = 0;
    pollCountRef.current = 0;

    const doPoll = async () => {
      try {
        const data = await getQuestions(noteId);

        if (data.status === 'asked' && data.questions.length > 0) {
          setQuestions(data.questions);
          setUiStatus('asked');
          clearTimer();
          return; // terminal — stop polling
        }

        if (TERMINAL_STATUSES.includes(data.status)) {
          setUiStatus('hidden');
          clearTimer();
          return; // terminal
        }

        // Still pending — schedule next poll
        schedulePoll(doPoll);
      } catch {
        // Network error — schedule next poll anyway (don't crash UI)
        schedulePoll(doPoll);
      }
    };

    // Fire the first poll immediately (but inside the schedule loop so the
    // interval is applied from the start to keep the budget accurate).
    schedulePoll(doPoll);

    return () => clearTimer();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [noteId]);

  // -----------------------------------------------------------------------
  // Handlers
  // -----------------------------------------------------------------------

  const handleDismiss = async () => {
    clearTimer();
    try {
      await dismiss(noteId);
    } catch {
      // Non-critical — still hide the sheet
    }
    setUiStatus('hidden');
    onComplete?.();
  };

  const handleSubmit = async () => {
    const trimmed = answerText.trim();
    if (!trimmed || isSubmitting) return;
    setIsSubmitting(true);
    try {
      await answer(noteId, trimmed);
      setUiStatus('hidden');
      onComplete?.();
    } catch {
      setIsSubmitting(false);
    }
  };

  const handleVoiceToggle = async () => {
    if (recorder.isRecording) {
      setIsTranscribing(true);
      const blob = await recorder.stop();
      if (blob) {
        // Upload blob to the standard voice upload endpoint for transcription
        try {
          const formData = new FormData();
          formData.append('file', blob, 'reflection.webm');
          const { useAuthStore } = await import('../store/authStore');
          const { accessToken } = useAuthStore.getState();
          const res = await fetch('/api/upload/audio', {
            method: 'POST',
            headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
            body: formData,
          });
          if (res.ok) {
            const data = (await res.json()) as { transcription?: string };
            if (data.transcription) {
              setAnswerText((prev) => prev ? `${prev} ${data.transcription}` : data.transcription!);
            }
          }
        } catch {
          // Transcription failed — user still has audio recorded, no-op
        }
      }
      setIsTranscribing(false);
    } else {
      await recorder.start();
    }
  };

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  if (uiStatus !== 'asked') return null;

  return (
    <div
      className="fixed bottom-0 left-0 right-0 z-40 animate-slide-up"
      aria-label="Shadow Reader — follow-up questions"
    >
      <div className="bg-gradient-to-t from-slate-900 to-slate-800 border-t border-indigo-500/30 rounded-t-3xl p-5 shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-indigo-400" aria-hidden="true" />
            <span className="text-sm text-slate-300">Want to go deeper?</span>
          </div>
          <button
            type="button"
            onClick={() => void handleDismiss()}
            className="text-slate-500 hover:text-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-400 rounded"
            aria-label="Dismiss shadow reader"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>

        {/* Questions */}
        <div className="space-y-2 mb-4">
          {questions.map((q, idx) => (
            <p key={idx} className="text-base text-slate-100 leading-relaxed">
              {q}
            </p>
          ))}
        </div>

        {/* Answer area */}
        <div className="flex gap-2">
          <textarea
            value={answerText}
            onChange={(e) => setAnswerText(e.target.value)}
            placeholder="Reflect briefly… (or skip)"
            rows={2}
            className="flex-1 bg-slate-950 rounded-xl px-3 py-2 text-sm resize-none text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            aria-label="Reflection answer"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                void handleSubmit();
              }
            }}
          />
          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={isSubmitting || !answerText.trim()}
              className="bg-indigo-600 p-2 rounded-xl hover:bg-indigo-500 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-indigo-400"
              aria-label="Submit reflection"
            >
              <Send className="w-4 h-4" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => void handleVoiceToggle()}
              disabled={isTranscribing}
              className={[
                'p-2 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-400',
                recorder.isRecording
                  ? 'bg-red-600 hover:bg-red-500 animate-pulse'
                  : 'bg-slate-700 hover:bg-slate-600',
                isTranscribing ? 'opacity-50' : '',
              ].join(' ')}
              aria-label={recorder.isRecording ? 'Stop voice recording' : 'Start voice recording'}
            >
              <Mic className="w-4 h-4" aria-hidden="true" />
            </button>
          </div>
        </div>

        {/* Partial transcript preview while recording */}
        {recorder.isRecording && recorder.partialText && (
          <p className="mt-2 text-xs text-slate-400 italic truncate">
            {recorder.partialText}
          </p>
        )}
      </div>
    </div>
  );
}
