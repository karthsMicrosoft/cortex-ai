import { useState } from 'react';
import type { Category } from '../db';
import { useNotes } from '../hooks/useNotes';
import { NoteCard } from '../components/NoteCard';
import { SyncIndicator } from '../components/SyncIndicator';
import { CATEGORY_COLORS } from '../utils/formatters';

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
 */
export default function LibraryPage(): React.ReactElement {
  const [activeCategory, setActiveCategory] = useState<Category | undefined>(undefined);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const notes = useNotes({
    category: activeCategory,
    dateFrom: dateFrom ? new Date(dateFrom) : undefined,
    dateTo: dateTo ? new Date(dateTo) : undefined,
  });

  return (
    <div className="flex min-h-screen flex-col bg-[#0F172A] pb-24">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
        <h1 className="text-lg font-semibold text-slate-100">Library</h1>
        <SyncIndicator />
      </header>

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
          notes.map((note) => <NoteCard key={note.localId} note={note} />)
        )}
      </main>
    </div>
  );
}
