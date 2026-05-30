import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

interface MockUser {
  id: string;
  email: string;
  display_name?: string;
}

interface MockAuthState {
  accessToken: string | null;
  user: MockUser | null;
  isRestoring: boolean;
  setAccessToken: (token: string) => void;
  login: (token: string, user: MockUser) => void;
  setRestoring: (value: boolean) => void;
}

const { mockAuthState, mockUseAuthStore } = vi.hoisted(() => {
  const mockAuthState = {} as MockAuthState;
  Object.assign(mockAuthState, {
    accessToken: null,
    user: null,
    isRestoring: false,
    setAccessToken: vi.fn((token: string) => {
      mockAuthState.accessToken = token;
    }),
    login: vi.fn((token: string, user: MockUser) => {
      mockAuthState.accessToken = token;
      mockAuthState.user = user;
      mockAuthState.isRestoring = false;
    }),
    setRestoring: vi.fn((value: boolean) => {
      mockAuthState.isRestoring = value;
    }),
  });

  const mockUseAuthStore = Object.assign(
    (selector: (state: MockAuthState) => unknown) => selector(mockAuthState),
    {
      getState: () => mockAuthState,
      subscribe: vi.fn(() => () => {}),
      setState: vi.fn((partial: Partial<MockAuthState>) => {
        Object.assign(mockAuthState, partial);
      }),
    },
  );

  return { mockAuthState, mockUseAuthStore };
});

vi.mock('../api/auth', () => ({
  refresh: vi.fn(() => Promise.reject(new Error('no cookie'))),
  me: vi.fn(),
}));

vi.mock('../sync/syncManager', () => ({
  syncManager: { start: vi.fn(), stop: vi.fn() },
}));

vi.mock('../services/shareInbox', () => ({
  drain: vi.fn(),
}));

vi.mock('../store/authStore', () => ({ useAuthStore: mockUseAuthStore }));

import { SessionGate } from '../components/SessionGate';
import { db, type LocalNote } from '../db';
import { setCachedUserId } from '../services/localUserData';
import { drain as drainShareInbox } from '../services/shareInbox';
import { syncManager } from '../sync/syncManager';

function setAuth(user: MockUser | null, accessToken: string | null): void {
  mockAuthState.accessToken = accessToken;
  mockAuthState.user = user;
  mockAuthState.isRestoring = false;
}

function seedNote(localId = 'note-1'): LocalNote {
  return {
    localId,
    content: 'seeded note',
    sourceType: 'text',
    category: 'Ideas',
    tags: [],
    syncStatus: 'pending',
    processingStatus: 'raw',
    createdAt: new Date('2026-05-30T00:00:00.000Z'),
    updatedAt: new Date('2026-05-30T00:00:00.000Z'),
  };
}

async function clearAllTables(): Promise<void> {
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
}

function renderSessionGate(): void {
  render(
    <MemoryRouter>
      <SessionGate>
        <div>child</div>
      </SessionGate>
    </MemoryRouter>,
  );
}

describe('SessionGate user-change local data isolation', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    localStorage.clear();
    setAuth(null, null);
    await clearAllTables();
  });

  afterEach(() => {
    cleanup();
  });

  it('wipes local data before sync when the authenticated user differs from the cached user', async () => {
    setCachedUserId('user-A');
    await db.notes.add(seedNote());
    setAuth({ id: 'user-B', email: 'b@b.com' }, 'token-B');

    renderSessionGate();

    await waitFor(async () => {
      expect(await db.notes.count()).toBe(0);
    });
    expect(localStorage.getItem('cortex_last_user_id')).toBe('user-B');
    expect(syncManager.start).toHaveBeenCalled();
    expect(drainShareInbox).toHaveBeenCalled();
  });

  it('does not wipe local data when the authenticated user matches the cached user', async () => {
    setCachedUserId('user-A');
    await db.notes.add(seedNote());
    setAuth({ id: 'user-A', email: 'a@a.com' }, 'token-A');

    renderSessionGate();

    await waitFor(() => expect(syncManager.start).toHaveBeenCalledTimes(1));
    expect(await db.notes.count()).toBe(1);
    expect(localStorage.getItem('cortex_last_user_id')).toBe('user-A');
  });

  it('does not wipe first-ever login data and sets the cached user id', async () => {
    await db.notes.add(seedNote());
    setAuth({ id: 'user-C', email: 'c@c.com' }, 'token-C');

    renderSessionGate();

    await waitFor(() => expect(localStorage.getItem('cortex_last_user_id')).toBe('user-C'));
    expect(await db.notes.count()).toBe(1);
    expect(syncManager.start).toHaveBeenCalled();
  });

  it('stops sync and leaves Dexie and cached user id untouched when logged out', async () => {
    setCachedUserId('user-A');
    await db.notes.add(seedNote());
    setAuth(null, null);

    renderSessionGate();

    await waitFor(() => expect(syncManager.stop).toHaveBeenCalledTimes(1));
    expect(syncManager.start).not.toHaveBeenCalled();
    expect(drainShareInbox).not.toHaveBeenCalled();
    expect(await db.notes.count()).toBe(1);
    expect(localStorage.getItem('cortex_last_user_id')).toBe('user-A');
  });
});
