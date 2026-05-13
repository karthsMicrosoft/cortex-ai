/**
 * ShadowReaderPrompt — auto-rendering bottom-sheet for the Shadow Reader feature (US-8).
 *
 * Behaviour:
 *  - Polls /api/notes/{id}/shadow-reader on the B17 tiered schedule:
 *      • 10 × 2 s   (first 20 s)
 *      • 5  × 5 s   (next 25 s)
 *      • stops after status reaches a terminal state (asked / answered /
 *        dismissed / skipped) OR after the 45 s window expires.
 *  - When status === 'asked' the component auto-renders a bottom-sheet docked
 *    above the BottomNav (h-16 on mobile, gone on ≥ sm). This is NOT a
 *    role='dialog' modal — it does not block page interaction.
 *  - When status is anything else, the component returns null.
 *
 * Voice answer (Round 15 / PR #26 — FR-8.4 "User answers via voice or text"):
 *  - On desktop UAs we render a mic button alongside the textarea. Pressing it
 *    starts MediaRecorder via useVoiceRecorder (same MIME-probing pattern the
 *    main capture flow uses); pressing again stops recording, uploads the blob
 *    via POST /api/upload, then calls submitAudioAnswer(noteId, url, blob_path)
 *    which transcribes server-side and feeds the transcript into the same
 *    shadow-reader merge pipeline as the text answer.
 *  - On mobile UAs the mic is hidden entirely (DECISIONS § 22w — mobile uses
 *    the file-only voice paths). The textarea remains the supported input.
 *  - The previous PR #14 mic was removed because it called a nonexistent
 *    /api/upload/audio endpoint; this revival uses the working /api/upload
 *    helper plus a new /shadow-reader/answer-audio backend endpoint.
 */

import { useCallback, useEffect, useState } from 'react';
import { Mic, Send, Sparkles, Square, X } from 'lucide-react';
import {
  answer,
  dismiss,
  getQuestions,
  submitAudioAnswer,
} from '../api/shadowReader';
import type { ShadowReaderStatus } from '../api/shadowReader';
import { apiUrl } from '../api/client';
import { isMobile, useVoiceRecorder } from '../hooks/useVoiceRecorder';
import { useAuthStore } from '../store/authStore';

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
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hidden, setHidden] = useState(false); // user dismissed/answered locally

  const recorder = useVoiceRecorder();

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

    // PERF-N2: Fire the first poll immediately (setTimeout(0) rather than the
    // tier delay) so the user doesn't wait 2s before the first check. Uses
    // setTimeout(…,0) instead of a bare void call so fake-timer test mocks
    // can drain the microtask queue deterministically.
    timerId = setTimeout(() => { void runPoll(); }, 0);

    return () => {
      cancelled = true;
      if (timerId) {
        clearTimeout(timerId);
        timerId = null;
      }
    };
  }, [noteId]);

  // -------------------------------------------------------------------------
  // Actions — dismiss / text answer
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
  // Voice answer (FR-8.4 / Round 15) — desktop only
  // -------------------------------------------------------------------------
  const uploadAndSubmitAudio = useCallback(
    async (blob: Blob) => {
      const token = useAuthStore.getState().accessToken;
      const ext = blob.type.includes('mp4')
        ? 'mp4'
        : blob.type.includes('ogg')
          ? 'ogg'
          : 'webm';
      const form = new FormData();
      form.append('file', blob, `shadow-reader-${Date.now()}.${ext}`);

      const uploadResp = await fetch(apiUrl('/api/upload'), {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        credentials: 'include',
        body: form,
      });
      if (!uploadResp.ok) {
        throw new Error(`Upload failed: ${uploadResp.status}`);
      }
      const { url, blob_path: blobPath } = (await uploadResp.json()) as {
        url: string;
        blob_path: string;
      };
      await submitAudioAnswer(noteId, url, blobPath);
    },
    [noteId],
  );

  const handleMicClick = useCallback(async () => {
    setError(null);
    if (!isRecording) {
      try {
        await recorder.start();
        setIsRecording(true);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : 'Could not start recording',
        );
      }
      return;
    }

    // Second click → stop + upload + transcribe.
    setIsRecording(false);
    setIsTranscribing(true);
    try {
      const blob = await recorder.stop();
      if (!blob) {
        throw new Error('Recording was empty');
      }
      await uploadAndSubmitAudio(blob);
      setHidden(true);
      onComplete?.();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message || 'Voice transcription failed'
          : 'Voice transcription failed',
      );
    } finally {
      setIsTranscribing(false);
    }
  }, [isRecording, recorder, uploadAndSubmitAudio, onComplete]);

  // -------------------------------------------------------------------------
  // Render — auto-show only when status === 'asked' and not locally hidden
  // -------------------------------------------------------------------------
  if (hidden) return null;
  if (status !== 'asked' || questions.length === 0) return null;

  return (
    <div
      // Bottom-sheet positioned ABOVE the BottomNav (h-16 = 64px). On ≥ sm the
      // BottomNav is hidden, so the sheet sits closer to the bottom edge.
      // NOT a role='dialog' — does not block page interaction.
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

        {isTranscribing && (
          <p className="mb-3 text-xs text-indigo-300" role="status">
            Transcribing…
          </p>
        )}

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
          {!isMobile && (
            <button
              type="button"
              onClick={() => void handleMicClick()}
              disabled={isTranscribing}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:opacity-50 ${
                isRecording
                  ? 'bg-red-600/80 text-white hover:bg-red-500'
                  : 'bg-slate-800 text-slate-200 hover:bg-slate-700'
              }`}
              aria-label={isRecording ? 'Stop recording' : 'Record voice answer'}
            >
              {isRecording ? (
                <Square className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Mic className="h-4 w-4" aria-hidden="true" />
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
