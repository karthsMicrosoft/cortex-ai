/**
 * ShadowReaderPrompt — auto-rendering bottom-sheet for the Shadow Reader feature (US-8).
 *
 * Behaviour (Round-4 revert 2026-05-01 — bug 16):
 *  - Polls /api/notes/{id}/shadow-reader on the B17 tiered schedule:
 *      • 10 × 2 s   (first 20 s)
 *      • 5  × 5 s   (next 25 s)
 *      • stops after status reaches a terminal state (asked / answered /
 *        dismissed / skipped) OR after the 45 s window expires.
 *  - When status === 'asked' the component auto-renders a bottom-sheet docked
 *    above the BottomNav (h-16 on mobile, gone on ≥ sm). This is NOT a
 *    role='dialog' modal — it does not block page interaction.
 *  - When status is anything else, the component returns null (renders nothing).
 *  - Voice mic was REMOVED in the previous revision — it called a non-existent
 *    /api/upload/audio endpoint and on failure left the page rendering
 *    "(recording pending transcription…)". Text-only answers stay; voice
 *    answer is a P3 follow-up.
 */

import { useCallback, useEffect, useState } from 'react';
import { Send, Sparkles, X } from 'lucide-react';
import { answer, dismiss, getQuestions } from '../api/shadowReader';
import type { ShadowReaderStatus } from '../api/shadowReader';

interface Props {
  noteId: string;
  onComplete?: () => void;
}

const TERMINAL_STATUSES: ReadonlySet<ShadowReaderStatus> = new Set([
  'asked',
  'answered',
  'dismissed',
  'skipped',
]);

const FAST_TIER_INTERVAL_MS = 2000;
const FAST_TIER_POLLS = 10;
const SLOW_TIER_INTERVAL_MS = 5000;
const SLOW_TIER_POLLS = 5;

export function ShadowReaderPrompt({ noteId, onComplete }: Props): React.ReactElement | null {
  const [status, setStatus] = useState<ShadowReaderStatus>('pending');
  const [questions, setQuestions] = useState<string[]>([]);
  const [answerText, setAnswerText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hidden, setHidden] = useState(false); // user dismissed/answered locally

  // -------------------------------------------------------------------------
  // Polling — B17 tiered schedule (10×2s, then 5×5s, total 45s window)
  // -------------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    let timerId: ReturnType<typeof setTimeout> | null = null;
    let pollCount = 0;

    const scheduleNext = () => {
      if (cancelled) return;
      if (pollCount >= FAST_TIER_POLLS + SLOW_TIER_POLLS) return;
      const delay =
        pollCount < FAST_TIER_POLLS ? FAST_TIER_INTERVAL_MS : SLOW_TIER_INTERVAL_MS;
      timerId = setTimeout(() => {
        // void wrap — fire-and-forget so the timer fires synchronously and the
        // promise chain settles via microtasks.
        void runPoll();
      }, delay);
    };

    const runPoll = async () => {
      if (cancelled) return;
      pollCount += 1;
      let data;
      try {
        data = await getQuestions(noteId);
      } catch {
        // Best-effort polling — swallow transient errors and try again.
        scheduleNext();
        return;
      }
      if (cancelled) return;
      setStatus(data.status);
      if (data.status === 'asked') {
        setQuestions(data.questions);
      }
      if (TERMINAL_STATUSES.has(data.status)) {
        // Reached a terminal state — stop polling.
        return;
      }
      scheduleNext();
    };

    scheduleNext();

    return () => {
      cancelled = true;
      if (timerId) {
        clearTimeout(timerId);
        timerId = null;
      }
    };
  }, [noteId]);

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------
  const handleDismiss = useCallback(async () => {
    try {
      await dismiss(noteId);
    } catch {
      // best-effort
    }
    setHidden(true);
    onComplete?.();
  }, [noteId, onComplete]);

  const handleSubmit = useCallback(async () => {
    const trimmed = answerText.trim();
    if (!trimmed || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await answer(noteId, trimmed);
      setHidden(true);
      onComplete?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit reflection');
    } finally {
      setIsSubmitting(false);
    }
  }, [answerText, isSubmitting, noteId, onComplete]);

  // -------------------------------------------------------------------------
  // Render — auto-show only when status === 'asked' and not locally hidden
  // -------------------------------------------------------------------------
  if (hidden) return null;
  if (status !== 'asked' || questions.length === 0) return null;

  return (
    <div
      // Bottom-sheet positioned ABOVE the BottomNav (h-16 = 64px). On ≥ sm the
      // BottomNav is hidden, so the sheet sits closer to the bottom edge.
      // NOT a role='dialog' — does not block page interaction (the UI
      // non-blocking guarantee in ShadowReaderPrompt.test.tsx).
      className="fixed inset-x-0 bottom-20 z-30 mx-auto w-full max-w-md px-4 sm:bottom-6"
      aria-label="Shadow Reader"
      data-testid="shadow-reader-sheet"
    >
      <div className="rounded-3xl border border-indigo-500/30 bg-slate-900/95 p-5 shadow-2xl backdrop-blur">
        {/* Header */}
        <div className="mb-3 flex items-start justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-indigo-400" aria-hidden="true" />
            <span className="text-sm font-medium text-slate-200">Want to go deeper?</span>
          </div>
          <button
            type="button"
            onClick={() => void handleDismiss()}
            className="rounded p-1 text-slate-500 hover:text-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            aria-label="Dismiss Shadow Reader prompt"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {/* Questions */}
        <ul className="mb-4 space-y-2">
          {questions.map((q, idx) => (
            <li key={idx} className="text-base leading-relaxed text-slate-100">
              {q}
            </li>
          ))}
        </ul>

        {/* Answer textarea */}
        <textarea
          value={answerText}
          onChange={(e) => setAnswerText(e.target.value)}
          placeholder="Reflect briefly…"
          rows={3}
          className="mb-3 w-full resize-none rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          aria-label="Reflection answer"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              void handleSubmit();
            }
          }}
        />

        {error && (
          <p className="mb-3 text-xs text-red-400" role="alert">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={() => void handleDismiss()}
            className="rounded-lg px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          >
            Skip
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={isSubmitting || !answerText.trim()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            aria-label="Submit reflection"
          >
            <Send className="h-4 w-4" aria-hidden="true" />
            {isSubmitting ? 'Saving…' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
}
