import { useCallback, useEffect, useState } from 'react';
import { useLiveQuery } from 'dexie-react-hooks';
import { db } from '../db';
import { syncManager } from '../sync/syncManager';

// ---------------------------------------------------------------------------
// Return type
// ---------------------------------------------------------------------------

export interface UseSyncReturn {
  /** Number of items waiting in the sync queue */
  pendingCount: number;
  /** True while pushChanges() is running */
  isSyncing: boolean;
  /** Manually trigger a push */
  pushNow: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * useSync — exposes `pendingCount`, `isSyncing`, `pushNow()` for
 * SyncIndicator and Settings.
 *
 * Live-queries Dexie so the count updates automatically when the queue drains.
 *
 * PERF-07 fix: replaced 500ms setInterval polling of syncManager.syncing with
 * an event subscription via syncManager.onSyncingChange().  React state is
 * updated only on actual transitions, eliminating the 2×/s re-render churn.
 */
export function useSync(): UseSyncReturn {
  const [isSyncing, setIsSyncing] = useState(false);

  const pendingCount = useLiveQuery(
    () => db.syncQueue.count(),
    [],
    0,
  );

  // Subscribe to syncing state changes via event emitter (PERF-07)
  useEffect(() => {
    const unsubscribe = syncManager.onSyncingChange(setIsSyncing);
    return unsubscribe;
  }, []);

  const pushNow = useCallback(async () => {
    // pushChanges() fires onSyncingChange internally; no manual setIsSyncing needed
    await syncManager.pushChanges();
  }, []);

  return {
    pendingCount: pendingCount ?? 0,
    isSyncing,
    pushNow,
  };
}
