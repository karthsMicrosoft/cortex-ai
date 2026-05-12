/**
 * Phase 5 / PR 5.1 — SharePage
 *
 * Public route landed on after the user picks Cortex from the OS share sheet.
 * The PWA manifest declares share_target as GET with title/text/url params
 * (see public/manifest.json), so the payload arrives via useSearchParams().
 *
 * Behavior:
 *   • No auth                 → enqueue payload, redirect to /login
 *   • Authed + URL only       → POST /api/import/url, navigate to /library
 *   • Authed + text(+url)     → POST /api/notes, navigate to /library
 *   • Failed save             → show error + retry
 *   • Empty payload           → empty-state message
 */

import { useEffect, useState } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2, AlertCircle } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { createNote } from '../api/notes';
import { importUrl } from '../api/import';
import { enqueue as enqueueShare, composeNoteBody } from '../services/shareInbox';

type Status = 'idle' | 'saving' | 'error' | 'stashed';

export default function SharePage(): React.ReactElement {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const accessToken = useAuthStore((s) => s.accessToken);

  const title = searchParams.get('title') ?? undefined;
  const text = searchParams.get('text') ?? undefined;
  const url = searchParams.get('url') ?? undefined;
  const hasPayload = Boolean(title || text || url);

  const [status, setStatus] = useState<Status>(hasPayload ? 'saving' : 'idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [redirectToLogin, setRedirectToLogin] = useState(false);

  async function processShare(): Promise<void> {
    setErrorMsg(null);
    setStatus('saving');

    // Unauthenticated: stash + redirect to /login.
    if (!accessToken) {
      try {
        await enqueueShare({ title, text, url });
      } catch {
        // Fall through — redirect to /login regardless so the user can sign in
        // and re-share. Surfacing a Dexie error here would be confusing.
      }
      setStatus('stashed');
      setRedirectToLogin(true);
      return;
    }

    try {
      const hasText = Boolean((text ?? '').trim());
      const hasTitle = Boolean((title ?? '').trim());
      let noteId: string | undefined;

      if (url && !hasText && !hasTitle) {
        const note = await importUrl({ url, title });
        noteId = note.id;
      } else {
        const content = composeNoteBody({ title, text, url });
        const note = await createNote({
          content,
          source_type: 'text',
        });
        noteId = note.id;
      }

      // Navigate to the library, highlighting the freshly-created note so the
      // user has a clear visual confirmation.
      const dest = noteId ? `/library?highlight=${encodeURIComponent(noteId)}` : '/library';
      navigate(dest, { replace: true });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save shared content';
      setErrorMsg(message);
      setStatus('error');
    }
  }

  useEffect(() => {
    if (!hasPayload) {
      setStatus('idle');
      return;
    }
    void processShare();
    // Run once on mount with the captured payload + auth state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (redirectToLogin) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="min-h-screen bg-[#0F172A] flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-slate-800 rounded-2xl p-6 space-y-4 text-center">
        <h1 className="text-2xl font-bold text-white">Cortex</h1>

        {!hasPayload && (
          <p className="text-slate-400" data-testid="share-empty">
            Nothing to share — open this page from your share sheet.
          </p>
        )}

        {hasPayload && status === 'saving' && (
          <div
            role="status"
            aria-label="Saving shared content"
            className="flex flex-col items-center gap-3 text-slate-300"
          >
            <Loader2 className="h-6 w-6 animate-spin text-indigo-400" />
            <p>Saving link…</p>
          </div>
        )}

        {status === 'stashed' && (
          <p className="text-slate-300">Sign in to finish saving this share…</p>
        )}

        {status === 'error' && (
          <div className="space-y-3">
            <div
              role="alert"
              className="bg-red-900/40 border border-red-500 text-red-300 rounded-lg p-3 text-sm flex items-start gap-2"
            >
              <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
              <span>{errorMsg ?? 'Failed to save shared content. Please try again.'}</span>
            </div>
            <button
              type="button"
              onClick={() => { void processShare(); }}
              className="w-full bg-[#4F46E5] hover:bg-indigo-700 text-white font-semibold rounded-lg py-2 px-4 transition-colors"
            >
              Retry
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
