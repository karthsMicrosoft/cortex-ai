/**
 * Task 4.1 (Zustand authStore) — TDD red
 *
 * Tests that authStore.ts exports a Zustand store with:
 *   - State: accessToken (string | null), user (User | null)
 *   - Actions: login(token, user), logout(), setAccessToken(token)
 *   - Token stored in MEMORY only (not localStorage / sessionStorage)
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const authStoreMocks = vi.hoisted(() => ({
  clearLocalUserData: vi.fn().mockResolvedValue(undefined),
  logoutApi: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../services/localUserData', () => ({
  clearLocalUserData: authStoreMocks.clearLocalUserData,
}));

vi.mock('../api/auth', () => ({
  logout: authStoreMocks.logoutApi,
}));

import { useAuthStore } from '../store/authStore';

// Helper: reset store between tests by calling logout
function resetStore() {
  useAuthStore.getState().logout();
}

describe('authStore — Zustand auth state (Task 4.1)', () => {
  beforeEach(() => {
    resetStore();
  });

  // ----------- initial state -----------

  it('initial accessToken is null', () => {
    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it('initial user is null', () => {
    expect(useAuthStore.getState().user).toBeNull();
  });

  // ----------- login action -----------

  it('login sets accessToken', () => {
    const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.sig';
    const user = { id: 'user-1', email: 'test@example.com', display_name: 'Test User' };
    useAuthStore.getState().login(token, user);
    expect(useAuthStore.getState().accessToken).toBe(token);
  });

  it('login sets user', () => {
    const token = 'tok-abc';
    const user = { id: 'user-2', email: 'alice@example.com', display_name: 'Alice' };
    useAuthStore.getState().login(token, user);
    expect(useAuthStore.getState().user).toEqual(user);
  });

  // ----------- logout action -----------

  it('logout clears accessToken', () => {
    const user = { id: 'u1', email: 'a@b.com', display_name: 'A' };
    useAuthStore.getState().login('some-token', user);
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it('logout clears user', () => {
    const user = { id: 'u1', email: 'a@b.com', display_name: 'A' };
    useAuthStore.getState().login('tok', user);
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().user).toBeNull();
  });

  // ----------- setAccessToken action -----------

  it('setAccessToken updates only the token (user remains unchanged)', () => {
    const user = { id: 'u3', email: 'bob@c.com', display_name: 'Bob' };
    useAuthStore.getState().login('old-token', user);
    useAuthStore.getState().setAccessToken('new-token');
    expect(useAuthStore.getState().accessToken).toBe('new-token');
    expect(useAuthStore.getState().user).toEqual(user);
  });

  it('setAccessToken can set token when no user is logged in', () => {
    useAuthStore.getState().setAccessToken('refreshed-token');
    expect(useAuthStore.getState().accessToken).toBe('refreshed-token');
  });

  // ----------- memory-only guarantee -----------

  it('token is NOT persisted to localStorage', () => {
    const token = 'secret-access-token';
    const user = { id: 'u4', email: 'd@e.com', display_name: 'D' };
    useAuthStore.getState().login(token, user);
    // Scan all localStorage keys for the token value
    const localStorageValues = Object.values(localStorage).join('|');
    expect(localStorageValues).not.toContain(token);
  });

  it('token is NOT persisted to sessionStorage', () => {
    const token = 'secret-session-token';
    const user = { id: 'u5', email: 'e@f.com', display_name: 'E' };
    useAuthStore.getState().login(token, user);
    const sessionValues = Object.values(sessionStorage).join('|');
    expect(sessionValues).not.toContain(token);
  });
});

// ----------- User type shape -----------
describe('User type shape', () => {
  it('user object has id, email, display_name', () => {
    const user: import('../store/authStore').User = {
      id: 'abc',
      email: 'x@y.com',
      display_name: 'X',
    };
    expect(user.id).toBe('abc');
    expect(user.email).toBe('x@y.com');
    // display_name is optional in some flows but type should allow string
    expect(user.display_name).toBe('X');
  });
});

describe('authStore — signOut wipes local user data (Round 29)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authStoreMocks.logoutApi.mockResolvedValue(undefined);
    authStoreMocks.clearLocalUserData.mockResolvedValue(undefined);
    resetStore();
  });

  it('signOut calls clearLocalUserData', async () => {
    const user = { id: 'u-round-29', email: 'round29@example.com', display_name: 'Round 29' };
    useAuthStore.getState().login('round-29-token', user);

    await useAuthStore.getState().signOut();

    expect(authStoreMocks.logoutApi).toHaveBeenCalledTimes(1);
    expect(authStoreMocks.clearLocalUserData).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it('signOut clears accessToken and user even if clearLocalUserData rejects', async () => {
    const user = { id: 'u-dexie-error', email: 'dexie@example.com', display_name: 'Dexie Error' };
    authStoreMocks.clearLocalUserData.mockRejectedValueOnce(new Error('Dexie clear failed'));
    useAuthStore.getState().login('token-before-dexie-error', user);

    await useAuthStore.getState().signOut();

    expect(authStoreMocks.clearLocalUserData).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().isRestoring).toBe(false);
  });

  it('signOut still clears state when the backend logout API throws', async () => {
    const user = { id: 'u-logout-error', email: 'logout@example.com', display_name: 'Logout Error' };
    authStoreMocks.logoutApi.mockRejectedValueOnce(new Error('Backend logout failed'));
    useAuthStore.getState().login('token-before-logout-error', user);

    await useAuthStore.getState().signOut();

    expect(authStoreMocks.logoutApi).toHaveBeenCalledTimes(1);
    expect(authStoreMocks.clearLocalUserData).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().isRestoring).toBe(false);
  });
});
