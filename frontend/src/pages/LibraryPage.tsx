import { useCallback, useState } from 'react';
import { Trash2, X } from 'lucide-react';
import { db } from '../db';
import type { Category } from '../db';
import { useNotes } from '../hooks/useNotes';
import { NoteCard } from '../components/NoteCard';
import { SyncIndicator } from '../components/SyncIndicator';
import { CATEGORY_COLORS } from '../utils/formatters';
import { apiUrl } from '../api/client';
import { useAuthStore } from '../store/authStore';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CATEGORIES: Category[] = ['Music', 'Fitness', 'Journal', 'Ideas', 'Spiritual', 'Learning'];

// ---------------------------------------------------------------------------
// LibraryPage
// ---------------------------------------------------------------------------

/**
 * LibraryPage — chronological timeline of notes.
 *
 * - Category filter chips (six fixed)
 * - Date range selector
 * - Reads from Dexie via useNotes (useLiveQuery) — offline-first
 * - Bug 3 (2026-05-01): select mode + bulk delete
 *     • Tap "Select" to enter select mode
 *     • Tap a note to toggle selection
 *     • "Delete" button appears once one or more notes are selected
 *     • Calls POST /api/notes/bulk-delete; backend cascades to blob storage
 */
export default function LibraryPage(): React.ReactElement {
  const [activeCategory, setActiveCategory] = useState<Category | undefined>(undefined);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [selectMode, setSelectMode] = useState(false);
  const [selectedLocalIds, setSelectedLocalIds] = useState<Set<string>>(new Set());
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const notes = useNotes({
    category: activeCategory,
    dateFrom: dateFrom ? new Date(dateFrom) : undefined,
    dateTo: dateTo ? new Date(dateTo) : undefined,
  });

  const toggleSelect = useCallback((localId: string) => {
    setSelectedLocalIds((prev) => {
      const next = new Set(prev);
      if (next.has(localId)) next.delete(localId);
      else next.add(localId);
      return next;
    });
  }, []);

  const exitSelectMode = useCallback(() => {
    setSelectMode(false);
    setSelectedLocalIds(new Set());
    setDeleteError(null);
  }, []);

  const handleBulkDelete = useCallback(async () => {
    if (selectedLocalIds.size === 0) return;
    if (!window.confirm(`Delete ${selectedLocalIds.size} note(s)? This cannot be undone.`)) return;

    setIsDeleting(true);
    setDeleteError(null);
    try {
      // Partition selected notes into synced (have serverId) vs local-only.
      const selectedNotes = notes.filter((n) => selectedLocalIds.has(n.localId));
      const serverIds = selectedNotes
        .map((n) => n.serverId)
        .filter((id): id is string => typeof id === 'string');

      if (serverIds.length > 0) {
        const token = useAuthStore.getState().accessToken;
        const res = await fetch(apiUrl('/api/notes/bulk-delete'), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          credentials: 'include',
          body: JSON.stringify({ ids: serverIds }),
        });
        if (!res.ok) {
          throw new Error(`Bulk delete failed: ${res.status}`);
        }
      }

      // Remove from local Dexie regardless (server already deleted these +
      // local-only notes need cleanup too)
      await db.notes.bulkDelete(selectedNotes.map((n) => n.localId));

      // Drop any pending sync queue entries for these notes
      const queueEntries = await db.syncQueue.toArray();
      const stale = queueEntries.filter((q) =>
        selectedNotes.some((n) => n.localId === q.entityId),
      );
      await db.syncQueue.bulkDelete(stale.map((q) => q.id!).filter(Boolean));

      exitSelectMode();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setIsDeleting(false);
    }
  }, [notes, selectedLocalIds, exitSelectMode]);

  return (
    <div className="flex min-h-screen flex-col bg-[#0F172A] pb-24">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
        <h1 className="text-lg font-semibold text-slate-100">Library</h1>
        <div className="flex items-center gap-2">
          {!selectMode && notes.length > 0 && (
            <button
              type="button"
              onClick={() => setSelectMode(true)}
              className="text-xs text-slate-400 hover:text-slate-200"
              data-testid="library-select-toggle"
            >
              Select
            </button>
          )}
          {selectMode && (
            <>
              <span className="text-xs text-slate-400" data-testid="library-selected-count">
                {selectedLocalIds.size} selected
              </span>
              <button
                type="button"
                onClick={() => void handleBulkDelete()}
                disabled={isDeleting || selectedLocalIds.size === 0}
                className="inline-flex items-center gap-1 rounded-md bg-red-600 px-2 py-1 text-xs font-semibold text-white hover:bg-red-500 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-red-400"
                data-testid="library-bulk-delete"
                aria-label="Delete selected notes"
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                {isDeleting ? 'Deleting…' : 'Delete'}
              </button>
              <button
                type="button"
                onClick={exitSelectMode}
                className="rounded-md p-1 text-slate-400 hover:bg-slate-800"
                aria-label="Cancel selection"
              >
                <X className="h-4 w-4" />
              </button>
            </>
          )}
          <SyncIndicator />
        </div>
      </header>

      {deleteError && (
        <div role="alert" className="border-b border-red-700/40 bg-red-900/30 px-4 py-2 text-xs text-red-300">
          {deleteError}
        </div>
      )}

      {/* Filters */}
      <div className="border-b border-slate-700/50 px-4 py-3">
        {/* Category chips */}
        <div className="mb-3 flex gap-2 overflow-x-auto pb-1">
          <button
            type="button"
            onClick={() => setActiveCategory(undefined)}
            className={[
              'shrink-0 rounded-full border px-3 py-1 text-xs font-medium transition-colors',
              activeCategory === undefined
                ? 'border-indigo-500 bg-indigo-900/50 text-indigo-200'
                : 'border-slate-600 bg-slate-800 text-slate-400 hover:border-slate-500',
            ].join(' ')}
          >
            All
          </button>
          {CATEGORIES.map((cat) => {
            const colors = CATEGORY_COLORS[cat];
            const isActive = activeCategory === cat;
            return (
              <button
                key={cat}
                type="button"
                onClick={() => setActiveCategory(isActive ? undefined : cat)}
                className={[
                  'shrink-0 rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                  isActive
                    ? `${colors.bg} ${colors.text} ${colors.border}`
                    : 'border-slate-600 bg-slate-800 text-slate-400 hover:border-slate-500',
                ].join(' ')}
              >
                {cat}
              </button>
            );
          })}
        </div>

        {/* Date range */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-slate-500">From</label>
          <input
            type="date"
            className="rounded-lg border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-slate-300 focus:border-indigo-500 focus:outline-none"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
          <label className="text-xs text-slate-500">To</label>
          <input
            type="date"
            className="rounded-lg border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-slate-300 focus:border-indigo-500 focus:outline-none"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
          {(dateFrom || dateTo) && (
            <button
              type="button"
              onClick={() => { setDateFrom(''); setDateTo(''); }}
              className="text-xs text-slate-500 underline hover:text-slate-300"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Timeline */}
      <main className="flex flex-1 flex-col gap-3 px-4 py-4">
        {notes.length === 0 ? (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-sm text-slate-500">No notes yet. Tap the mic to capture one!</p>
          </div>
        ) : (
          notes.map((note) => {
            const isSelected = selectedLocalIds.has(note.localId);
            return (
              <div key={note.localId} className="relative">
                {selectMode && (
                  <div className="absolute right-2 top-2 z-10 flex items-center justify-center">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelect(note.localId)}
                      onClick={(e) => e.stopPropagation()}
                      className="h-4 w-4 rounded border-slate-500 bg-slate-700 text-indigo-500 focus:ring-indigo-400"
                      aria-label={`Select note: ${note.content.slice(0, 60)}`}
                      data-testid={`library-select-${note.localId}`}
                    />
                  </div>
                )}
                <NoteCard
                  note={note}
                  onPress={selectMode ? toggleSelect : undefined}
                />
              </div>
            );
          })
        )}
      </main>
    </div>
  );
}
