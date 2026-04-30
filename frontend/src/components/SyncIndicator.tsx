import { useNavigate } from 'react-router-dom';
import { useLiveQuery } from 'dexie-react-hooks';
import { Wifi, WifiOff, RefreshCw, AlertTriangle } from 'lucide-react';
import { db } from '../db';
import { useSync } from '../hooks/useSync';

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * SyncIndicator — shows online/offline status + pending-queue count.
 *
 * - Subscribes live to Dexie syncQueue for the pending count.
 * - Shows a red badge with the conflict count and navigates to /conflicts.
 * - Tapping the sync icon manually triggers pushNow().
 */
export function SyncIndicator(): React.ReactElement {
  const navigate = useNavigate();
  const { isSyncing, pushNow } = useSync();

  const pendingCount = useLiveQuery(
    () => db.syncQueue.count(),
    [],
    0,
  );

  const conflictCount = useLiveQuery(
    () => db.notes.where('syncStatus').equals('conflict').count(),
    [],
    0,
  );

  const isOnline = typeof navigator !== 'undefined' ? navigator.onLine : true;

  return (
    <div className="flex items-center gap-2">
      {/* Online / offline icon */}
      {isOnline ? (
        <Wifi className="h-4 w-4 text-green-400" aria-label="Online" />
      ) : (
        <WifiOff className="h-4 w-4 text-slate-500" aria-label="Offline" />
      )}

      {/* Pending queue count */}
      {(pendingCount ?? 0) > 0 && (
        <button
          type="button"
          aria-label={`${pendingCount ?? 0} pending sync items — tap to sync now`}
          onClick={() => void pushNow()}
          className="flex items-center gap-1 rounded-full bg-amber-900/50 px-2 py-0.5 text-xs text-amber-300 hover:bg-amber-900/80 focus:outline-none focus:ring-2 focus:ring-amber-400"
        >
          <RefreshCw
            className={['h-3 w-3', isSyncing ? 'animate-spin' : ''].join(' ')}
            aria-hidden="true"
          />
          {pendingCount}
        </button>
      )}

      {/* Conflict count badge */}
      {(conflictCount ?? 0) > 0 && (
        <button
          type="button"
          aria-label={`${conflictCount ?? 0} sync conflicts — tap to resolve`}
          onClick={() => navigate('/conflicts')}
          className="flex items-center gap-1 rounded-full bg-red-900/60 px-2 py-0.5 text-xs text-red-300 hover:bg-red-900/80 focus:outline-none focus:ring-2 focus:ring-red-400"
        >
          <AlertTriangle className="h-3 w-3" aria-hidden="true" />
          Conflicts ({conflictCount})
        </button>
      )}
    </div>
  );
}

export default SyncIndicator;
