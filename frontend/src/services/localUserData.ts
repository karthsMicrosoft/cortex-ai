/**
 * localUserData.ts — per-user local data isolation.
 *
 * Why this exists (Round 29, 2026-05-30): the Dexie database `cortex-db`
 * is a SINGLETON keyed on the browser, not on the user. Before this module
 * existed, signing out of account A and signing in to account B left A's
 * notes sitting in IndexedDB — Library showed them, hover tooltips showed
 * them, and the next pull simply merged B's server notes on top.
 *
 * The fix is two-layered:
 *   1) `signOut()` calls `clearLocalUserData()` so the moment the user
 *      explicitly leaves, every trace of their notes is wiped from the
 *      browser. (Primary defense, see `authStore.signOut`.)
 *   2) `SessionGate` compares the incoming user id against the cached id
 *      from the last successful login. If they differ, it wipes before
 *      starting the sync engine. (Defense-in-depth — covers tab-closed-
 *      without-sign-out → different account opens the tab.)
 *
 * Backend canvases routes are not affected; this is purely a frontend
 * data-isolation problem.
 */

import { db } from '../db';
import { syncManager } from '../sync/syncManager';

const LAST_USER_ID_KEY = 'cortex_last_user_id';

/**
 * Workbox runtimeCaching cache names — keep in sync with `vite.config.ts`
 * (`VitePWA.workbox.runtimeCaching[].options.cacheName`). If these names
 * change there, mirror the change here or the SW cache will outlive
 * sign-out and serve user A's responses to user B for up to the cache TTL.
 */
const USER_RUNTIME_CACHES = ['api-cache', 'blob-cache'] as const;

export function getCachedUserId(): string | null {
  try {
    return localStorage.getItem(LAST_USER_ID_KEY);
  } catch {
    return null;
  }
}

export function setCachedUserId(userId: string): void {
  try {
    localStorage.setItem(LAST_USER_ID_KEY, userId);
  } catch {
    // Storage quota / privacy mode — non-fatal, defense-in-depth detection
    // simply degrades to "always trust the auth token, never wipe on user
    // change" until storage is writable again.
  }
}

export function clearCachedUserId(): void {
  try {
    localStorage.removeItem(LAST_USER_ID_KEY);
  } catch {
    // ignore
  }
}

/**
 * Wipe every byte of user-scoped data from the current browser:
 *
 *   - Dexie tables: notes, syncQueue, deadLetter, meta, shared_inbox
 *   - localStorage: cortex_last_user_id  (refresh token is handled separately
 *                   by `auth.logout()` so the order of operations is safe)
 *   - Workbox runtime caches: api-cache, blob-cache
 *
 * Stops the sync engine first so background pull / push cannot race the
 * clear and immediately re-populate `notes` with rows from the user we're
 * trying to forget about.
 *
 * Every step is wrapped in its own try/catch — losing one layer (e.g. a
 * Cache Storage API that isn't implemented in the current browser) must
 * never block the others.
 */
export async function clearLocalUserData(): Promise<void> {
  try {
    syncManager.stop();
  } catch {
    // syncManager may not have started yet — fine.
  }

  // --- Dexie ---
  try {
    if (!db.isOpen()) {
      await db.open();
    }
    await Promise.all([
      db.notes.clear(),
      db.syncQueue.clear(),
      db.deadLetter.clear(),
      db.meta.clear(),
      db.shared_inbox.clear(),
    ]);
  } catch {
    // Last-ditch: if a table failed to clear (e.g. schema migration in
    // flight), best we can do is leave the rows and rely on the next pull
    // to overwrite them. We still want to clear the rest of the surfaces.
  }

  // --- localStorage user-pointer ---
  clearCachedUserId();

  // --- Workbox runtime caches ---
  try {
    if (typeof caches !== 'undefined' && caches?.delete) {
      await Promise.all(
        USER_RUNTIME_CACHES.map((name) => caches.delete(name).catch(() => false)),
      );
    }
  } catch {
    // CacheStorage not implemented (older browsers / non-secure contexts)
    // — non-fatal.
  }
}
