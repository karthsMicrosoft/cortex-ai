import { useEffect } from 'react';
import { useLiveQuery } from 'dexie-react-hooks';
import { db } from '../db';
import type { LocalNote, Category, SyncStatus } from '../db';
import { syncManager } from '../sync/syncManager';

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

export interface NotesFilter {
  category?: Category;
  syncStatus?: SyncStatus;
  dateFrom?: Date;
  dateTo?: Date;
  limit?: number;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * useNotes — Dexie-backed hook that combines offline-first IndexedDB reads
 * with the pull flow (B13).
 *
 * - Uses `useLiveQuery` so the UI updates reactively when Dexie changes.
 * - Triggers a pull on mount and respects the `online` event.
 * - Merge/conflict logic lives in syncManager.pullChanges().
 *
 * PERF-09 fix: date range filters now use Dexie's .where('createdAt').between()
 * index scan instead of fetching all notes and filtering in JavaScript.  This
 * leverages the `createdAt` index defined in db.ts and avoids loading the full
 * note set into memory for narrow date queries on large local stores.
 */
export function useNotes(filter: NotesFilter = {}): LocalNote[] {
  // Live query from Dexie — reactive to all writes
  const notes = useLiveQuery(async () => {
    const { category, syncStatus, dateFrom, dateTo, limit } = filter;

    // Fast path: date-range query using the createdAt index (PERF-09)
    if (dateFrom || dateTo) {
      const lower = dateFrom ?? new Date(0);
      const upper = dateTo ?? new Date(8_640_000_000_000_000); // max JS date

      let collection = db.notes
        .where('createdAt')
        .between(lower, upper, true, true);

      let results = await collection.toArray();

      // Apply secondary filters in memory (these reduce an already-small set)
      if (category) {
        results = results.filter((n) => n.category === category);
      }
      if (syncStatus) {
        results = results.filter((n) => n.syncStatus === syncStatus);
      }

      // Sort newest-first (between() returns ascending by index)
      results = results.reverse();

      if (limit) {
        results = results.slice(0, limit);
      }
      return results;
    }

    // No date filter — use the original indexed queries
    let collection = db.notes.orderBy('createdAt').reverse();

    if (category) {
      collection = db.notes
        .where('category')
        .equals(category)
        .reverse();
    }

    if (syncStatus) {
      collection = db.notes
        .where('syncStatus')
        .equals(syncStatus)
        .reverse();
    }

    let results = await collection.toArray();

    if (limit) {
      results = results.slice(0, limit);
    }

    return results;
  }, [filter.category, filter.syncStatus, filter.dateFrom, filter.dateTo, filter.limit]);

  // Trigger pull on mount and on 'online' event
  useEffect(() => {
    void syncManager.pullChanges();

    const handleOnline = () => void syncManager.pullChanges();
    window.addEventListener('online', handleOnline);
    return () => window.removeEventListener('online', handleOnline);
  }, []);

  // Periodic pull every 60s while foreground
  useEffect(() => {
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') {
        void syncManager.pullChanges();
      }
    }, 60_000);

    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        void syncManager.pullChanges();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, []);

  return notes ?? [];
}
