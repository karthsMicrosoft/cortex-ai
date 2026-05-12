/**
 * LinkPicker — modal for creating manual links between notes (PR 6.3).
 *
 * UX flow:
 *   1. User clicks "+ Link to another note" in the BacklinksPanel.
 *   2. We render a centered modal with a debounced search input.
 *   3. As the user types, we GET /api/notes?q=… (debounced 300ms) and render
 *      matching notes as clickable cards (the current note is filtered out).
 *   4. Clicking a card moves to a confirmation step that posts to
 *      POST /api/notes/{currentId}/links (link_type=manual).
 *   5. On success the parent's `onCreated` callback fires and the modal closes
 *      (so the BacklinksPanel can refresh). On error we show inline text.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';
import { listNotes } from '../api/notes';
import type { NoteOut } from '../api/notes';
import { createManualLink } from '../api/links';

interface LinkPickerProps {
  sourceNoteId: string;
  onClose: () => void;
  onCreated: () => void;
}

const DEBOUNCE_MS = 300;
const MAX_RESULTS = 20;

function _label(note: NoteOut): string {
  if (note.title && note.title.trim().length > 0) return note.title;
  const snippet = (note.content || '').trim().split(/\s+/).slice(0, 8).join(' ');
  return snippet.length > 0 ? snippet : '(untitled note)';
}

export function LinkPicker({
  sourceNoteId,
  onClose,
  onCreated,
}: LinkPickerProps): React.ReactElement {
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [results, setResults] = useState<NoteOut[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [pendingTarget, setPendingTarget] = useState<NoteOut | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);

  // Focus the search input on mount.
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Debounce the query — flush after 300ms of inactivity.
  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedQuery(query), DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [query]);

  // Run the search whenever the debounced query changes.
  useEffect(() => {
    let cancelled = false;
    const trimmed = debouncedQuery.trim();
    if (trimmed.length === 0) {
      setResults([]);
      setIsSearching(false);
      return () => {
        cancelled = true;
      };
    }
    setIsSearching(true);
    setError(null);
    void listNotes({ q: trimmed, limit: MAX_RESULTS })
      .then((resp) => {
        if (cancelled) return;
        // Filter out the current note — you can't link a note to itself.
        setResults(resp.items.filter((n) => n.id !== sourceNoteId));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Search failed');
        setResults([]);
      })
      .finally(() => {
        if (!cancelled) setIsSearching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery, sourceNoteId]);

  // Close on Escape (only when not submitting).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isSubmitting) {
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isSubmitting, onClose]);

  const handleConfirm = useCallback(async () => {
    if (!pendingTarget || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await createManualLink(sourceNoteId, pendingTarget.id);
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create link');
      setIsSubmitting(false);
    }
  }, [pendingTarget, isSubmitting, sourceNoteId, onCreated, onClose]);

  const overlayClassName = useMemo(
    () =>
      'fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 pt-16 sm:items-center sm:pt-4',
    [],
  );

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Link to another note"
      className={overlayClassName}
      onClick={(e) => {
        // Click outside the panel closes the modal.
        if (e.target === e.currentTarget && !isSubmitting) onClose();
      }}
    >
      <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-4 shadow-xl">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200">Link to another note</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close"
            className="rounded-md p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200 disabled:opacity-50"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {pendingTarget ? (
          <div className="mt-4 flex flex-col gap-3">
            <p className="text-xs text-slate-400">Create a manual link to:</p>
            <div className="rounded-xl border border-indigo-500/40 bg-slate-800/60 p-3">
              <p className="text-sm text-slate-100">{_label(pendingTarget)}</p>
              <p className="mt-1 text-xs text-slate-500">{pendingTarget.category}</p>
            </div>
            {error && (
              <p role="alert" className="text-xs text-red-400">
                {error}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setPendingTarget(null);
                  setError(null);
                }}
                disabled={isSubmitting}
                className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
              >
                Back
              </button>
              <button
                type="button"
                onClick={() => void handleConfirm()}
                disabled={isSubmitting}
                className="rounded-md bg-indigo-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-400 disabled:opacity-50"
              >
                {isSubmitting ? 'Linking…' : 'Confirm link'}
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="mt-3 flex items-center gap-2 rounded-md border border-slate-700 bg-slate-800/60 px-2">
              <Search className="h-4 w-4 text-slate-500" aria-hidden="true" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search notes by title or content…"
                aria-label="Search notes"
                className="flex-1 bg-transparent py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none"
              />
            </div>

            <div
              className="mt-3 max-h-72 overflow-y-auto"
              data-testid="link-picker-results"
            >
              {isSearching && (
                <p className="text-xs text-slate-500" aria-label="Searching">
                  Searching…
                </p>
              )}
              {!isSearching && error && (
                <p role="alert" className="text-xs text-red-400">
                  {error}
                </p>
              )}
              {!isSearching && !error && debouncedQuery.trim().length === 0 && (
                <p className="text-xs text-slate-500">
                  Start typing to find a note to link to.
                </p>
              )}
              {!isSearching &&
                !error &&
                debouncedQuery.trim().length > 0 &&
                results.length === 0 && (
                  <p className="text-xs text-slate-500">No matching notes.</p>
                )}
              {!isSearching && results.length > 0 && (
                <ul className="flex flex-col gap-2">
                  {results.map((note) => (
                    <li key={note.id}>
                      <button
                        type="button"
                        onClick={() => setPendingTarget(note)}
                        className="w-full rounded-xl border border-slate-700 bg-slate-800/40 p-3 text-left transition-colors hover:border-indigo-500/50 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                      >
                        <p className="line-clamp-2 text-sm text-slate-200">
                          {_label(note)}
                        </p>
                        <p className="mt-1 text-xs text-slate-500">{note.category}</p>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
