/**
 * localUserData.test.ts — Round 29 (2026-05-30)
 *
 * Tests for the per-user data isolation helper. Verifies that
 * clearLocalUserData() actually wipes every surface where user A's data
 * could otherwise leak into user B's session.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { db } from '../db';
import {
  clearLocalUserData,
  getCachedUserId,
  setCachedUserId,
  clearCachedUserId,
} from '../services/localUserData';

// syncManager has its own pull/push side effects — stub the singleton to
// keep the unit isolated.
vi.mock('../sync/syncManager', () => ({
  syncManager: {
    start: vi.fn(),
    stop: vi.fn(),
  },
}));

import { syncManager } from '../sync/syncManager';

// ---------------------------------------------------------------------------
// CacheStorage stub (jsdom doesn't ship one)
// ---------------------------------------------------------------------------

interface FakeCaches {
  delete: ReturnType<typeof vi.fn>;
  _deleted: string[];
}

function installFakeCaches(): FakeCaches {
  const deleted: string[] = [];
  const fake: FakeCaches = {
    _deleted: deleted,
    delete: vi.fn(async (name: string) => {
      deleted.push(name);
      return true;
    }),
  };
  Object.defineProperty(globalThis, 'caches', {
    value: fake,
    configurable: true,
    writable: true,
  });
  return fake;
}

function uninstallCaches(): void {
  Object.defineProperty(globalThis, 'caches', {
    value: undefined,
    configurable: true,
    writable: true,
  });
}

// ---------------------------------------------------------------------------
// Helpers — seed Dexie with sample rows so we can prove they get cleared
// ---------------------------------------------------------------------------

async function seedDexie(): Promise<void> {
  if (!db.isOpen()) await db.open();
  await db.notes.add({
    localId: 'note-leak-1',
    content: 'leaked content',
    sourceType: 'text',
    category: 'Ideas',
    tags: [],
    syncStatus: 'synced',
    processingStatus: 'enriched',
    createdAt: new Date('2026-01-01'),
    updatedAt: new Date('2026-01-01'),
  });
  await db.syncQueue.add({
    operation: 'create',
    entityType: 'note',
    entityId: 'note-leak-1',
    payload: {},
    timestamp: new Date('2026-01-01'),
    retryCount: 0,
  });
  await db.deadLetter.add({
    operation: 'update',
    entityType: 'note',
    entityId: 'note-leak-2',
    payload: {},
    timestamp: new Date('2026-01-02'),
    retryCount: 6,
    failedAt: new Date('2026-01-02'),
  });
  await db.meta.put({ key: 'lastPullCursor', value: '2026-05-29T00:00:00Z' });
  await db.shared_inbox.add({
    text: 'leaked share-target text',
    created_at: '2026-05-30T00:00:00Z',
  });
}

async function countAllUserScopedTables(): Promise<Record<string, number>> {
  return {
    notes: await db.notes.count(),
    syncQueue: await db.syncQueue.count(),
    deadLetter: await db.deadLetter.count(),
    meta: await db.meta.count(),
    shared_inbox: await db.shared_inbox.count(),
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('localUserData — getCachedUserId / setCachedUserId / clearCachedUserId', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('round-trips a user id through localStorage', () => {
    expect(getCachedUserId()).toBeNull();
    setCachedUserId('user-abc');
    expect(getCachedUserId()).toBe('user-abc');
  });

  it('clearCachedUserId removes the entry', () => {
    setCachedUserId('user-abc');
    clearCachedUserId();
    expect(getCachedUserId()).toBeNull();
  });

  it('persists under the documented localStorage key cortex_last_user_id', () => {
    setCachedUserId('user-xyz');
    expect(localStorage.getItem('cortex_last_user_id')).toBe('user-xyz');
  });
});

describe('localUserData — clearLocalUserData wipes every user-scoped surface', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    localStorage.clear();
    // Make sure Dexie starts empty before each test.
    if (!db.isOpen()) await db.open();
    await Promise.all([
      db.notes.clear(),
      db.syncQueue.clear(),
      db.deadLetter.clear(),
      db.meta.clear(),
      db.shared_inbox.clear(),
    ]);
  });

  afterEach(() => {
    uninstallCaches();
  });

  it('clears all five user-scoped Dexie tables', async () => {
    await seedDexie();
    const before = await countAllUserScopedTables();
    expect(before).toEqual({
      notes: 1,
      syncQueue: 1,
      deadLetter: 1,
      meta: 1,
      shared_inbox: 1,
    });

    await clearLocalUserData();

    const after = await countAllUserScopedTables();
    expect(after).toEqual({
      notes: 0,
      syncQueue: 0,
      deadLetter: 0,
      meta: 0,
      shared_inbox: 0,
    });
  });

  it('removes the cortex_last_user_id pointer from localStorage', async () => {
    setCachedUserId('user-being-forgotten');
    await clearLocalUserData();
    expect(localStorage.getItem('cortex_last_user_id')).toBeNull();
  });

  it('stops the sync engine before clearing so a pull cannot race', async () => {
    await clearLocalUserData();
    expect(vi.mocked(syncManager.stop)).toHaveBeenCalledTimes(1);
  });

  it('deletes the Workbox runtimeCaching caches (api-cache + blob-cache)', async () => {
    const fake = installFakeCaches();
    await clearLocalUserData();
    expect(fake._deleted).toContain('api-cache');
    expect(fake._deleted).toContain('blob-cache');
    expect(fake.delete).toHaveBeenCalledTimes(2);
  });

  it('is a no-op-safe when the CacheStorage API is missing', async () => {
    uninstallCaches();
    // Should not throw.
    await expect(clearLocalUserData()).resolves.toBeUndefined();
  });

  it('is safe to call when Dexie is already empty', async () => {
    await expect(clearLocalUserData()).resolves.toBeUndefined();
    const after = await countAllUserScopedTables();
    expect(after).toEqual({
      notes: 0,
      syncQueue: 0,
      deadLetter: 0,
      meta: 0,
      shared_inbox: 0,
    });
  });

  it('continues clearing other surfaces even if one cache.delete rejects', async () => {
    const deleted: string[] = [];
    Object.defineProperty(globalThis, 'caches', {
      value: {
        delete: vi.fn(async (name: string) => {
          deleted.push(name);
          if (name === 'api-cache') throw new Error('boom');
          return true;
        }),
      },
      configurable: true,
      writable: true,
    });

    setCachedUserId('user-still-cached');
    await seedDexie();

    await clearLocalUserData();

    expect(deleted).toContain('api-cache');
    expect(deleted).toContain('blob-cache');
    expect(localStorage.getItem('cortex_last_user_id')).toBeNull();
    const after = await countAllUserScopedTables();
    expect(after.notes).toBe(0);
  });
});
