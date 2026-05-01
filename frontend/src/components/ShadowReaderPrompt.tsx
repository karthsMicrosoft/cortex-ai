/**
 * ShadowReaderPrompt — opt-in modal for the Shadow Reader feature (US-8).
 *
 * Behaviour (revised 2026-05-01 to address bugs 8 + 10):
 *  - Renders a small "Want to go deeper?" launcher button in the page chrome.
 *    The user clicks it to open the modal — NO auto-pop, NO bottom-sheet
 *    that randomly appears mid-scroll.
 *  - On open, fetches /api/notes/{noteId}/shadow-reader.
 *      • status === 'asked' + questions → show questions + textarea
 *      • status === 'pending'            → "Questions are still generating…"
 *      • everything else                 → "No active prompt for this note"
 *  - Send → POST /api/notes/{id}/shadow-reader/answer; modal closes.
 *  - Voice mic was REMOVED: it called a non-existent /api/upload/audio
 *    endpoint and on failure left the page rendering
 *    "(recording pending transcription…)". Text-only answers for now;
 *    voice answer is P3 follow-up.
 */

import { useCallback, useEffect, useState } from 'react';
import { Send, Sparkles, X } from 'lucide-react';
import { answer, dismiss, getQuestions } from '../api/shadowReader';
import type { ShadowReaderStatus } from '../api/shadowReader';

interface Props {
  noteId: string;
  onComplete?: () => void;
}

type ModalState =
  | { kind: 'closed' }
  | { kind: 'loading' }
  | { kind: 'asked'; questions: string[] }
  | { kind: 'pending' }
  | { kind: 'unavailable'; status: ShadowReaderStatus };

export function ShadowReaderPrompt({ noteId, onComplete }: Props): React.ReactElement | null {
  const [modal, setModal] = useState<ModalState>({ kind: 'closed' });
  const [answerText, setAnswerText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = useCallback(async () => {
    setModal({ kind: 'loading' });
    setError(null);
    try {
      const data = await getQuestions(noteId);
      if (data.status === 'asked' && data.questions.length > 0) {
        setModal({ kind: 'asked', questions: data.questions });
        return;
      }
      if (data.status === 'pending') {
        setModal({ kind: 'pending' });
        return;
      }
      setModal({ kind: 'unavailable', status: data.status });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load follow-up questions');
      setModal({ kind: 'closed' });
    }
  }, [noteId]);

  const close = useCallback(() => {
    setModal({ kind: 'closed' });
    setAnswerText('');
    setError(null);
  }, []);

  const handleDismiss = useCallback(async () => {
    try {
      await dismiss(noteId);
    } catch {
      // Best-effort — close the modal regardless
    }
    close();
    onComplete?.();
  }, [noteId, close, onComplete]);

  const handleSubmit = useCallback(async () => {
    const trimmed = answerText.trim();
    if (!trimmed || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await answer(noteId, trimmed);
      close();
      onComplete?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit reflection');
    } finally {
      setIsSubmitting(false);
    }
  }, [answerText, isSubmitting, noteId, close, onComplete]);

  // Trigger an open() on demand from outside (e.g. a header button on the
  // detail page). For now, the button is rendered inline below.
  useEffect(() => {
    // No-op — modal stays closed until the user clicks the launcher.
  }, []);

  const isOpen = modal.kind !== 'closed';

  return (
    <>
      {/* Launcher — always visible (Bug 8 fix: persistent button instead of
         random bottom-sheet popups) */}
      <button
        type="button"
        onClick={() => void open()}
        className="inline-flex items-center gap-2 rounded-full border border-indigo-500/40 bg-indigo-900/30 px-3 py-1.5 text-xs font-medium text-indigo-200 hover:bg-indigo-900/60 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        aria-label="Open Shadow Reader follow-up prompt"
        data-testid="shadow-reader-launcher"
      >
        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
        Want to go deeper?
      </button>

      {/* Modal overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 sm:items-center"
          role="dialog"
          aria-modal="true"
          aria-label="Shadow Reader"
          onClick={close}
        >
          <div
            className="w-full max-w-md rounded-t-3xl border-t border-indigo-500/30 bg-slate-900 p-5 shadow-2xl sm:rounded-3xl sm:border"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="mb-3 flex items-start justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-indigo-400" aria-hidden="true" />
                <span className="text-sm font-medium text-slate-200">Want to go deeper?</span>
              </div>
              <button
                type="button"
                onClick={close}
                className="rounded p-1 text-slate-500 hover:text-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                aria-label="Close"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>

            {/* Body */}
            {modal.kind === 'loading' && (
              <p className="text-sm text-slate-400">Loading…</p>
            )}

            {modal.kind === 'pending' && (
              <p className="text-sm text-slate-400">
                Follow-up questions are still being generated. Please try again in a few seconds.
              </p>
            )}

            {modal.kind === 'unavailable' && (
              <p className="text-sm text-slate-400">
                {modal.status === 'answered'
                  ? 'You already answered the prompt for this note.'
                  : modal.status === 'dismissed'
                  ? 'You dismissed the prompt for this note.'
                  : modal.status === 'skipped'
                  ? 'No prompt was generated for this note.'
                  : 'No active prompt for this note.'}
              </p>
            )}

            {modal.kind === 'asked' && (
              <>
                <ul className="mb-4 space-y-2">
                  {modal.questions.map((q, idx) => (
                    <li key={idx} className="text-base leading-relaxed text-slate-100">
                      {q}
                    </li>
                  ))}
                </ul>

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
                  <p className="mb-3 text-xs text-red-400" role="alert">{error}</p>
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
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
