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
 */
export function useSync(): UseSyncReturn {
  const [isSyncing, setIsSyncing] = useState(false);

  const pendingCount = useLiveQuery(
    () => db.syncQueue.count(),
    [],
    0,
  );

  // Keep isSyncing in sync with the singleton's state via polling
  useEffect(() => {
    const interval = setInterval(() => {
      setIsSyncing(syncManager.syncing);
    }, 500);
    return () => clearInterval(interval);
  }, []);

  const pushNow = useCallback(async () => {
    setIsSyncing(true);
    try {
      await syncManager.pushChanges();
    } finally {
      setIsSyncing(false);
    }
  }, []);

  return {
    pendingCount: pendingCount ?? 0,
    isSyncing,
    pushNow,
  };
}
