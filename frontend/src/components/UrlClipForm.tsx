/**
 * Phase 5 / PR 5.3 — UrlClipForm
 *
 * Compact form that wraps `frontend/src/api/import.ts::importUrl()`. Used by
 * CapturePage's "URL" tab (and potentially by a future browser-extension popup
 * if we choose to share the component).
 *
 * Surfaces friendly, status-code-aware messaging so the user knows whether the
 * page was rejected for being too large, internal, unreadable, etc. — the
 * server-side rules live in `backend/app/api/import_url.py` (PR 5.2).
 */

import { useState } from 'react';
import { Link as LinkIcon, Loader2, Send, X } from 'lucide-react';
import { importUrl } from '../api/import';
import { ApiError } from '../api/client';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface UrlClipFormProps {
  onSuccess?: (noteId: string) => void;
  onCancel?: () => void;
  initialUrl?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Cheap client-side URL sanity check. The server is the source of truth, but
 * we use this to enable/disable the Save button so the user gets immediate
 * feedback on obviously-broken input (e.g. "not a url").
 */
function isLikelyValidUrl(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return false;
  // Accept bare hosts ("example.com") by trying with an inferred scheme.
  const candidate = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
  try {
    const u = new URL(candidate);
    if (!u.hostname || !u.hostname.includes('.')) return false;
    if (/\s/.test(trimmed)) return false;
    return true;
  } catch {
    return false;
  }
}

/** Map known HTTP status codes to user-friendly copy. */
function messageForError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 400:
        return 'Invalid URL.';
      case 403:
        return "Cannot fetch from internal IPs.";
      case 413:
        return 'Page too large (> 5 MB).';
      case 415:
        return 'Page format not supported.';
      case 422:
        return 'No readable content extracted.';
      case 502:
      case 504:
        return "Couldn't fetch the page (try again later).";
      default:
        return err.detail || err.message || 'Something went wrong. Try again.';
    }
  }
  if (err instanceof Error && err.message) return err.message;
  return 'Something went wrong. Try again.';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function UrlClipForm({
  onSuccess,
  onCancel,
  initialUrl = '',
}: UrlClipFormProps): React.ReactElement {
  const [url, setUrl] = useState(initialUrl);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedNoteId, setSavedNoteId] = useState<string | null>(null);

  const canSubmit = !isSaving && isLikelyValidUrl(url);

  async function handleSubmit(e?: React.FormEvent): Promise<void> {
    e?.preventDefault();
    if (!canSubmit) return;

    setError(null);
    setIsSaving(true);
    try {
      const note = await importUrl({ url: url.trim() });
      setSavedNoteId(note.id);
      onSuccess?.(note.id);
    } catch (err) {
      setError(messageForError(err));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e);
      }}
      className="rounded-xl border border-slate-700 bg-slate-800/60 p-4"
    >
      <label
        htmlFor="url-clip-input"
        className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-400"
      >
        URL
      </label>
      <div className="relative">
        <LinkIcon
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
          aria-hidden="true"
        />
        <input
          id="url-clip-input"
          type="url"
          autoFocus
          inputMode="url"
          autoComplete="url"
          spellCheck={false}
          placeholder="https://example.com/article"
          value={url}
          onChange={(e) => {
            setUrl(e.target.value);
            if (error) setError(null);
            if (savedNoteId) setSavedNoteId(null);
          }}
          disabled={isSaving}
          className="w-full rounded-lg border border-slate-600 bg-slate-900 py-2 pl-9 pr-3 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-60"
        />
        {isSaving ? (
          <div
            role="status"
            aria-label="Saving link"
            className="absolute inset-0 flex items-center justify-end pr-3"
          >
            <Loader2
              className="h-4 w-4 animate-spin text-indigo-300"
              aria-hidden="true"
            />
          </div>
        ) : null}
      </div>

      {error ? (
        <p
          role="alert"
          className="mt-3 rounded-md border border-red-700/40 bg-red-900/30 p-2 text-sm text-red-200"
        >
          {error}
        </p>
      ) : null}

      {savedNoteId ? (
        <p
          role="status"
          className="mt-3 rounded-md border border-emerald-700/40 bg-emerald-900/30 p-2 text-sm text-emerald-200"
        >
          Saved!
        </p>
      ) : null}

      <div className="mt-3 flex items-center justify-end gap-2">
        {onCancel ? (
          <button
            type="button"
            onClick={onCancel}
            disabled={isSaving}
            className="flex items-center gap-1.5 rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-slate-300 hover:border-slate-500 hover:text-slate-100 disabled:opacity-50"
          >
            <X className="h-4 w-4" aria-hidden="true" />
            Cancel
          </button>
        ) : null}
        <button
          type="submit"
          disabled={!canSubmit}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:opacity-50"
        >
          {isSaving ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Saving…
            </>
          ) : (
            <>
              <Send className="h-4 w-4" aria-hidden="true" />
              Save link
            </>
          )}
        </button>
      </div>
    </form>
  );
}

export default UrlClipForm;
