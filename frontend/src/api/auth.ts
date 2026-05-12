import { apiGet, apiPost, apiPut } from './client';
import type { User } from '../store/authStore';

// ---------------------------------------------------------------------------
// Response shapes
// ---------------------------------------------------------------------------

export interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
  // Round-7: refresh_token now also in the JSON body for localStorage fallback.
  // Cookie delivery is preserved as defense-in-depth.
  refresh_token: string;
}

export interface RegisterResponse {
  // UserOut fields (flat — mirroring the backend RegisterResponse schema)
  id: string;
  email: string;
  display_name?: string;
  shadow_reader_enabled: boolean;
  shadow_reader_disabled_categories: string[];
  // Tokens (Round-7 addition)
  access_token: string;
  token_type: 'bearer';
  refresh_token: string;
}

export interface RefreshResponse {
  access_token: string;
  refresh_token: string;
}

// ---------------------------------------------------------------------------
// localStorage key for the refresh token (Round-7 cookie-fallback)
// ---------------------------------------------------------------------------

const REFRESH_STORAGE_KEY = 'cortex_refresh';

// ---------------------------------------------------------------------------
// Auth API functions
// ---------------------------------------------------------------------------

/**
 * Login with email + password.
 * Stores refresh_token in localStorage so refresh works even when Edge
 * "Balanced" tracking-prevention blocks the third-party httpOnly cookie.
 */
export async function login(email: string, password: string): Promise<LoginResponse> {
  const data = await apiPost<LoginResponse>('/api/auth/login', { email, password });
  if (data.refresh_token) {
    localStorage.setItem(REFRESH_STORAGE_KEY, data.refresh_token);
  }
  return data;
}

/**
 * Register a new account.
 * Stores refresh_token in localStorage (same rationale as login).
 */
export async function register(
  email: string,
  password: string,
  displayName?: string,
): Promise<RegisterResponse> {
  const data = await apiPost<RegisterResponse>('/api/auth/register', {
    email,
    password,
    display_name: displayName,
  });
  if (data.refresh_token) {
    localStorage.setItem(REFRESH_STORAGE_KEY, data.refresh_token);
  }
  return data;
}

/**
 * Refresh the access token.
 * Sends the stored refresh_token in the JSON body (Round-7 localStorage path).
 * Falls back to cookie-only if localStorage is empty (for browsers that honour
 * SameSite=None+Secure cookies across origins).
 * Rotates the stored refresh_token on success.
 */
export async function refresh(): Promise<RefreshResponse> {
  const storedRefresh = localStorage.getItem(REFRESH_STORAGE_KEY);
  const body = storedRefresh ? { refresh_token: storedRefresh } : undefined;
  const data = await apiPost<RefreshResponse>('/api/auth/refresh', body);
  if (data.refresh_token) {
    localStorage.setItem(REFRESH_STORAGE_KEY, data.refresh_token);
  }
  return data;
}

/**
 * Get the currently authenticated user.
 */
export async function me(): Promise<User> {
  return apiGet<User>('/api/auth/me');
}

/**
 * Update the authenticated user's profile (display_name).
 */
export async function updateProfile(displayName: string): Promise<User> {
  return apiPut<User>('/api/auth/me', { display_name: displayName });
}

/**
 * Change the authenticated user's password.
 */
export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  await apiPost<void>('/api/auth/password', {
    current_password: currentPassword,
    new_password: newPassword,
  });
}

// ---------------------------------------------------------------------------
// Browser-extension clip token (Round 17 / PR 5.5)
// ---------------------------------------------------------------------------

export interface ClipTokenResponse {
  clip_token: string;
  expires_in: number;
  scope: string;
}

/**
 * Mint a clip-scoped JWT for the browser extension.
 *
 * Calls `POST /api/auth/clip-token` using the user's current session token
 * (forwarded by the shared client/fetchWithAuth wrapper). Throws `ApiError`
 * on non-2xx responses.
 *
 * The returned token MUST NOT be persisted to localStorage / sessionStorage —
 * callers should keep it in component state only and surface a fresh mint
 * action when the user wants to revoke / rotate.
 */
export async function mintClipToken(): Promise<ClipTokenResponse> {
  return apiPost<ClipTokenResponse>('/api/auth/clip-token');
}

/**
 * Logout — revoke the refresh JTI, clear the httpOnly cookie, and remove the
 * localStorage token (Round-7 fallback cleanup).
 * Idempotent on the backend so a click during a stale session is safe.
 */
export async function logout(): Promise<void> {
  localStorage.removeItem(REFRESH_STORAGE_KEY);
  await apiPost<void>('/api/auth/logout');
}
