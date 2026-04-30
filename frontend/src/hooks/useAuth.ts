import { useEffect } from 'react';
import { useAuthStore, type User } from '../store/authStore';
import { me } from '../api/auth';

// ---------------------------------------------------------------------------
// useAuth — convenience hook
// ---------------------------------------------------------------------------

interface UseAuthReturn {
  /** Whether the user is authenticated (has a non-null accessToken) */
  isAuthenticated: boolean;
  /** The authenticated user, or null if not logged in */
  user: User | null;
  /** Log in with a token + user object (from loginApi response) */
  login: (token: string, user: User) => void;
  /** Clear auth state */
  logout: () => void;
}

/**
 * Hydrates the user profile via GET /api/auth/me on mount (if authenticated),
 * and exposes isAuthenticated, login, logout, user from authStore.
 */
export function useAuth(): UseAuthReturn {
  const accessToken = useAuthStore((s) => s.accessToken);
  const user = useAuthStore((s) => s.user);
  const { login, logout } = useAuthStore.getState();

  // On mount: if we have an access token but no user, fetch the profile
  useEffect(() => {
    if (accessToken && !user) {
      me()
        .then((profile) => {
          useAuthStore.getState().login(accessToken, profile);
        })
        .catch(() => {
          // Token is invalid or expired — clear auth state
          logout();
        });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    isAuthenticated: accessToken !== null,
    user,
    login,
    logout,
  };
}
