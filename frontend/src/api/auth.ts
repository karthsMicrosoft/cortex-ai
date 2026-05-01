import { apiGet, apiPost, apiPut } from './client';
import type { User } from '../store/authStore';

// ---------------------------------------------------------------------------
// Response shapes
// ---------------------------------------------------------------------------

export interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
  // SEC-02: refresh_token is delivered exclusively via httpOnly cookie — it is
  // NOT present in the JSON body and must not be read from the response object.
}

export interface RegisterResponse {
  id: string;
  email: string;
  display_name?: string;
}

export interface RefreshResponse {
  access_token: string;
}

// ---------------------------------------------------------------------------
// Auth API functions
// ---------------------------------------------------------------------------

/**
 * Login with email + password.
 * Returns access_token (refresh token is set as httpOnly cookie by backend).
 */
export async function login(email: string, password: string): Promise<LoginResponse> {
  return apiPost<LoginResponse>('/api/auth/login', { email, password });
}

/**
 * Register a new account.
 */
export async function register(
  email: string,
  password: string,
  displayName?: string,
): Promise<RegisterResponse> {
  return apiPost<RegisterResponse>('/api/auth/register', {
    email,
    password,
    display_name: displayName,
  });
}

/**
 * Refresh the access token using the httpOnly refresh cookie.
 */
export async function refresh(): Promise<RefreshResponse> {
  return apiPost<RefreshResponse>('/api/auth/refresh');
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

/**
 * Logout — revoke the refresh JTI and clear the httpOnly cookie.
 * Idempotent on the backend so a click during a stale session is safe.
 */
export async function logout(): Promise<void> {
  await apiPost<void>('/api/auth/logout');
}
