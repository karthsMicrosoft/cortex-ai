import { useEffect, type ReactNode } from 'react';
import { useAuthStore } from '../store/authStore';
import { refresh, me } from '../api/auth';
import { syncManager } from '../sync/syncManager';

/**
 * SessionGate — runs ONCE at app boot.
 *
 * Purpose: solve the "page refresh forces logout" symptom (live-deploy bug
 * R7). Access tokens are memory-only (SEC-02), so a hard reload wipes them.
 * The httpOnly refresh cookie however still lives in the browser; we use it
 * to mint a fresh access token, fetch the user, then start the sync engine.
 *
 * Flow on mount:
 *   1. POST /api/auth/refresh  (cookie → new access_token)
 *      • success → setAccessToken + me() → login(token, user)
 *      • failure (401, network, etc.) → silently fall through, user stays
 *        unauthenticated and AuthGate will redirect to /login
 *   2. Whether or not refresh succeeded, set isRestoring=false so the
 *      router stops showing the splash.
 *   3. After successful restore (or fresh login elsewhere), start the
 *      sync engine so the queue drains automatically.
 *
 * Renders the children regardless — the AuthGate per route is the actual
 * redirect surface. SessionGate only updates the auth store.
 */
export function SessionGate({ children }: { children: ReactNode }): React.ReactElement {
  const accessToken = useAuthStore((s) => s.accessToken);
  const isRestoring = useAuthStore((s) => s.isRestoring);

  // Step 1 — attempt session restore on first mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { access_token } = await refresh();
        if (cancelled) return;
        useAuthStore.getState().setAccessToken(access_token);
        const user = await me();
        if (cancelled) return;
        useAuthStore.getState().login(access_token, user);
      } catch {
        // No valid refresh cookie — leave user unauthenticated.
        if (!cancelled) {
          useAuthStore.getState().setRestoring(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // run once at mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Step 2 — start sync engine whenever we transition to "authenticated".
  // This covers both paths: SessionGate-restored sessions AND fresh logins.
  useEffect(() => {
    if (accessToken) {
      void syncManager.start();
    } else {
      syncManager.stop();
    }
  }, [accessToken]);

  // While we're still trying refresh on first load, show a splash so AuthGate
  // doesn't yank an authenticated user to /login during the round trip.
  if (isRestoring && !accessToken) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0F172A]">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  return <>{children}</>;
}
