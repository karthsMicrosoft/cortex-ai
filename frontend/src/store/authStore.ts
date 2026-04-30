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

  // Actions
  login: (token: string, user: User) => void;
  logout: () => void;
  setAccessToken: (token: string) => void;
}

// ---------------------------------------------------------------------------
// Store — no persistence middleware to ensure token stays in memory only
// ---------------------------------------------------------------------------

export const useAuthStore = create<AuthState>()((set) => ({
  accessToken: null,
  user: null,

  login: (token, user) => set({ accessToken: token, user }),

  logout: () => set({ accessToken: null, user: null }),

  setAccessToken: (token) => set({ accessToken: token }),
}));
