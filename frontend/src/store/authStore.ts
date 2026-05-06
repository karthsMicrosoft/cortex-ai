import { create } from 'zustand';

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

  setAccessToken: (token) => set({ accessToken: token }),
  setRestoring: (value) => set({ isRestoring: value }),
  setUser: (user) => set({ user }),
}));
