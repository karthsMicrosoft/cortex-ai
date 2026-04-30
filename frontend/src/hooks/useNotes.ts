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
 */
export function useNotes(filter: NotesFilter = {}): LocalNote[] {
  // Live query from Dexie — reactive to all writes
  const notes = useLiveQuery(async () => {
    let collection = db.notes.orderBy('createdAt').reverse();

    if (filter.category) {
      collection = db.notes
        .where('category')
        .equals(filter.category)
        .reverse();
    }

    if (filter.syncStatus) {
      collection = db.notes
        .where('syncStatus')
        .equals(filter.syncStatus)
        .reverse();
    }

    let results = await collection.toArray();

    if (filter.dateFrom) {
      results = results.filter((n) => n.createdAt >= filter.dateFrom!);
    }
    if (filter.dateTo) {
      results = results.filter((n) => n.createdAt <= filter.dateTo!);
    }
    if (filter.limit) {
      results = results.slice(0, filter.limit);
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
