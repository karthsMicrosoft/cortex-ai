import { apiGet, apiPost } from './client';
import type { User } from '../store/authStore';

// ---------------------------------------------------------------------------
// Response shapes
// ---------------------------------------------------------------------------

export interface LoginResponse {
  access_token: string;
  refresh_token?: string;
  token_type: 'bearer';
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
