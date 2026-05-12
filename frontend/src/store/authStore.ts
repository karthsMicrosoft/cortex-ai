import { create } from 'zustand';
import { logout as logoutApi } from '../api/auth';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface User {
  id: string;
  email: string;
  display_name?: string;
}

interface AuthState {
  /** Access token kept in memory only — never persisted to localStorage/sessionStorage */
  accessToken: string | null;
  /** Authenticated user profile */
  user: User | null;
  /**
   * Initial session restore is in flight. While true, AuthGate must NOT
   * redirect to /login — we don't yet know whether the httpOnly refresh
   * cookie can produce a session. Set to false after refresh+me() finish
   * (success or failure).
   */
  isRestoring: boolean;

  // Actions
  login: (token: string, user: User) => void;
  logout: () => void;
  /**
   * Async sign-out — best-effort backend revoke (POST /api/auth/logout) AND
   * always clear local auth state. Safe to call from any UI handler; never
   * throws even if the network call fails (we still want the user signed out
   * locally).
   */
  signOut: () => Promise<void>;
  setAccessToken: (token: string) => void;
  setRestoring: (value: boolean) => void;
  setUser: (user: User) => void;
}

// ---------------------------------------------------------------------------
// Store — no persistence middleware to ensure token stays in memory only
// ---------------------------------------------------------------------------

export const useAuthStore = create<AuthState>()((set) => ({
  accessToken: null,
  user: null,
  // Default true: at app boot we ALWAYS attempt session-restore via /refresh
  // before letting AuthGate decide where to send the user.
  isRestoring: true,

  login: (token, user) => set({ accessToken: token, user, isRestoring: false }),

  logout: () => set({ accessToken: null, user: null, isRestoring: false }),

  signOut: async () => {
    try {
      await logoutApi();
    } catch {
      // Best-effort — even if backend revoke fails we still clear local state
      // (e.g. user is offline, token already expired, etc.)
    }
    set({ accessToken: null, user: null, isRestoring: false });
  },

  setAccessToken: (token) => set({ accessToken: token }),
  setRestoring: (value) => set({ isRestoring: value }),
  setUser: (user) => set({ user }),
}));
