/**
 * Task 4 — SyncManager — TDD red
 *
 * Tests `frontend/src/sync/syncManager.ts` (singleton class):
 *
 * Critical resolutions:
 *   - B11: pushChanges must handle imageBlob AND audioBlob branches
 *     (imageBlob → POST /api/upload → imageUrl; audioBlob → POST /api/upload → audioUrl)
 *     then POST /api/notes with returned URLs
 *   - B13: pullChanges fetches GET /api/sync/pull?since=<timestamp>
 *     Conflict detection: local.updatedAt > lastPull AND local.syncStatus !== 'synced'
 *     → sets syncStatus='conflict', conflictServerVersion = serverNote
 *   - Retry counter: bumps retryCount on failure; after 5 failures → deadLetter table
 *   - FIFO drain of syncQueue
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mock authStore — must come before importing syncManager
// ---------------------------------------------------------------------------

vi.mock('../store/authStore', () => ({
  useAuthStore: {
    getState: () => ({ accessToken: 'test-token-12345' }),
  },
}));

// ---------------------------------------------------------------------------
// Ensure navigator.onLine = true throughout tests
// ---------------------------------------------------------------------------

Object.defineProperty(navigator, 'onLine', { value: true, configurable: true, writable: true });

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const LAST_PULL_EPOCH = '1970-01-01T00:00:00Z';

const MOCK_AUDIO_BLOB = new Blob(['audio'], { type: 'audio/webm' });
const MOCK_IMAGE_BLOB = new Blob(['img-data'], { type: 'image/jpeg' });

const MOCK_SYNC_QUEUE_ITEM = {
  id: 1,
  operation: 'create' as const,
  entityType: 'note',
  entityId: 'local-id-1',
  payload: { localId: 'local-id-1' },
  timestamp: new Date(),
  retryCount: 0,
};

const MOCK_SYNC_QUEUE_IMAGE_ITEM = {
  id: 2,
  operation: 'create' as const,
  entityType: 'note',
  entityId: 'local-img-1',
  payload: { localId: 'local-img-1' },
  timestamp: new Date(),
  retryCount: 0,
};

const MOCK_LOCAL_NOTE_AUDIO = {
  localId: 'local-id-1',
  content: 'Test voice note',
  sourceType: 'voice',
  category: 'Ideas',
  tags: [],
  syncStatus: 'pending',
  processingStatus: 'raw',
  audioBlob: MOCK_AUDIO_BLOB,
  createdAt: new Date('2026-04-10T10:00:00Z'),
  updatedAt: new Date('2026-04-10T10:00:00Z'),
};

const MOCK_LOCAL_NOTE_IMAGE = {
  localId: 'local-img-1',
  content: 'Image note',
  sourceType: 'image',
  category: 'Ideas',
  tags: [],
  syncStatus: 'pending',
  processingStatus: 'raw',
  imageBlob: MOCK_IMAGE_BLOB,
  createdAt: new Date('2026-04-10T11:00:00Z'),
  updatedAt: new Date('2026-04-10T11:00:00Z'),
};

const UPLOAD_URL = 'https://storage.blob.core.windows.net/audio/test.webm';
const IMAGE_UPLOAD_URL = 'https://storage.blob.core.windows.net/images/test.jpg';
const CREATED_SERVER_NOTE = {
  id: 'server-uuid-1',
  content: 'Test voice note',
  source_type: 'voice',
  category: 'Ideas',
  processing_status: 'raw',
  sync_status: 'synced',
  tags: [],
  created_at: '2026-04-10T10:00:00Z',
  updated_at: '2026-04-10T10:00:00Z',
  entities: [],
  music_metadata: {},
  user_id: 'user-1',
};

const PULL_RESPONSE = {
  notes: [
    {
      id: 'server-pulled-1',
      content: 'Server note 1',
      source_type: 'text',
      category: 'Journal',
      processing_status: 'enriched',
      sync_status: 'synced',
      tags: [],
      created_at: '2026-04-11T00:00:00Z',
      updated_at: '2026-04-11T01:00:00Z',
      entities: [],
      music_metadata: {},
      user_id: 'user-1',
    },
  ],
  deletions: [] as string[],
  server_time: '2026-04-12T00:00:00Z',
};

// ---------------------------------------------------------------------------
// Stable mock state objects — mutated per test via .mockImplementation etc.
// ---------------------------------------------------------------------------

// Use stable spy objects that are always the same reference (vi.mock is hoisted)
const dbMocks = {
  notesGet: vi.fn(),
  notesUpdate: vi.fn(),
  notesAdd: vi.fn(),
  notesDelete: vi.fn(),
  notesWhereFirst: vi.fn(), // the .first() at end of where().equals().first()
  syncQueueToArray: vi.fn(),
  syncQueueUpdate: vi.fn(),
  syncQueueDelete: vi.fn(),
  deadLetterAdd: vi.fn(),
  metaGet: vi.fn(),
  metaPut: vi.fn(),
};

// The transaction calls the callback directly; internal db calls go through dbMocks
vi.mock('../db', () => {
  const makeNotes = () => ({
    get: (...args: unknown[]) => dbMocks.notesGet(...args),
    update: (...args: unknown[]) => dbMocks.notesUpdate(...args),
    add: (...args: unknown[]) => dbMocks.notesAdd(...args),
    delete: (...args: unknown[]) => dbMocks.notesDelete(...args),
    where: () => ({
      equals: () => ({ first: (...args: unknown[]) => dbMocks.notesWhereFirst(...args) }),
    }),
  });

  const makeSyncQueue = () => ({
    orderBy: () => ({ toArray: (...args: unknown[]) => dbMocks.syncQueueToArray(...args) }),
    update: (...args: unknown[]) => dbMocks.syncQueueUpdate(...args),
    delete: (...args: unknown[]) => dbMocks.syncQueueDelete(...args),
    add: vi.fn().mockResolvedValue(1),
  });

  return {
    db: {
      get notes() { return makeNotes(); },
      get syncQueue() { return makeSyncQueue(); },
      get deadLetter() { return { add: (...args: unknown[]) => dbMocks.deadLetterAdd(...args) }; },
      get meta() {
        return {
          get: (...args: unknown[]) => dbMocks.metaGet(...args),
          put: (...args: unknown[]) => dbMocks.metaPut(...args),
        };
      },
      transaction: async (_mode: string, _tables: unknown[], fn: () => Promise<void>) => fn(),
    },
  };
});

// ---------------------------------------------------------------------------
// Create fresh SyncManager instance (bypass singleton) per test
// ---------------------------------------------------------------------------

async function makeFreshSyncManager() {
  const mod = await import('../sync/syncManager');
  const SM = (mod as { SyncManager: { prototype: object } }).SyncManager;
  const instance = Object.create(SM.prototype) as {
    pushChanges: () => Promise<void>;
    pullChanges: () => Promise<void>;
    isSyncing: boolean;
  };
  instance.isSyncing = false;
  return instance;
}

// ---------------------------------------------------------------------------
// Fetch mock helper
// ---------------------------------------------------------------------------

function setupDefaultFetch(overrides: Record<string, unknown> = {}) {
  const mock = vi.fn().mockImplementation((url: string) => {
    if (url === '/api/upload') {
      return Promise.resolve({ ok: true, json: async () => ({ url: UPLOAD_URL }) });
    }
    if (url === '/api/notes') {
      return Promise.resolve({ ok: true, json: async () => CREATED_SERVER_NOTE });
    }
    if (typeof url === 'string' && url.includes('/api/sync/pull')) {
      return Promise.resolve({ ok: true, json: async () => overrides.pullResponse ?? PULL_RESPONSE });
    }
    return Promise.resolve({ ok: true, json: async () => ({}) });
  });
  vi.stubGlobal('fetch', mock);
  return mock;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SyncManager — module exports', () => {
  it('exports a syncManager singleton', async () => {
    const mod = await import('../sync/syncManager');
    expect((mod as Record<string, unknown>).syncManager).toBeDefined();
  });

  it('exports a SyncManager class', async () => {
    const mod = await import('../sync/syncManager');
    expect(typeof (mod as Record<string, unknown>).SyncManager).toBe('function');
  });

  it('syncManager has a pushChanges method', async () => {
    const mod = await import('../sync/syncManager');
    const sm = (mod as Record<string, unknown>).syncManager as { pushChanges: unknown };
    expect(typeof sm.pushChanges).toBe('function');
  });

  it('syncManager has a pullChanges method', async () => {
    const mod = await import('../sync/syncManager');
    const sm = (mod as Record<string, unknown>).syncManager as { pullChanges: unknown };
    expect(typeof sm.pullChanges).toBe('function');
  });
});

describe('SyncManager — pushChanges (Task 4.1 — B11)', () => {
  beforeEach(() => {
    // Reset all db mock fns
    dbMocks.notesGet.mockResolvedValue(MOCK_LOCAL_NOTE_AUDIO);
    dbMocks.notesUpdate.mockResolvedValue(undefined);
    dbMocks.notesAdd.mockResolvedValue('new-local-id');
    dbMocks.notesDelete.mockResolvedValue(undefined);
    dbMocks.notesWhereFirst.mockResolvedValue(null);
    dbMocks.syncQueueToArray.mockResolvedValue([MOCK_SYNC_QUEUE_ITEM]);
    dbMocks.syncQueueUpdate.mockResolvedValue(undefined);
    dbMocks.syncQueueDelete.mockResolvedValue(undefined);
    dbMocks.deadLetterAdd.mockResolvedValue(undefined);
    dbMocks.metaGet.mockResolvedValue({ key: 'lastPull', value: LAST_PULL_EPOCH });
    dbMocks.metaPut.mockResolvedValue(undefined);

    setupDefaultFetch();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    // Reset all mock call histories
    Object.values(dbMocks).forEach((m) => m.mockClear());
  });

  // --- pushChanges: audio branch ---

  it('pushChanges uploads audioBlob via POST /api/upload', async () => {
    const sm = await makeFreshSyncManager();
    await sm.pushChanges();

    const mockFetchFn = vi.mocked(global.fetch as ReturnType<typeof vi.fn>);
    const uploadCall = mockFetchFn.mock.calls.find((call) => call[0] === '/api/upload');
    expect(uploadCall).toBeDefined();
  });

  it('pushChanges creates note via POST /api/notes', async () => {
    const sm = await makeFreshSyncManager();
    await sm.pushChanges();

    const mockFetchFn = vi.mocked(global.fetch as ReturnType<typeof vi.fn>);
    const createCall = mockFetchFn.mock.calls.find((call) => call[0] === '/api/notes');
    expect(createCall).toBeDefined();
  });

  it('pushChanges sends audio_url in POST /api/notes body', async () => {
    const sm = await makeFreshSyncManager();
    await sm.pushChanges();

    const mockFetchFn = vi.mocked(global.fetch as ReturnType<typeof vi.fn>);
    const createCall = mockFetchFn.mock.calls.find((call) => call[0] === '/api/notes');
    expect(createCall).toBeDefined();
    const body = JSON.parse(createCall[1].body as string);
    expect(body.audio_url).toBe(UPLOAD_URL);
  });

  // --- pushChanges: image branch (B11) ---

  it('pushChanges uploads imageBlob via POST /api/upload when imageBlob present', async () => {
    dbMocks.notesGet.mockResolvedValue(MOCK_LOCAL_NOTE_IMAGE);
    dbMocks.syncQueueToArray.mockResolvedValue([MOCK_SYNC_QUEUE_IMAGE_ITEM]);

    let uploadCalled = false;
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url === '/api/upload') {
        uploadCalled = true;
        return Promise.resolve({ ok: true, json: async () => ({ url: IMAGE_UPLOAD_URL }) });
      }
      if (url === '/api/notes') {
        return Promise.resolve({ ok: true, json: async () => CREATED_SERVER_NOTE });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    }));

    const sm = await makeFreshSyncManager();
    await sm.pushChanges();

    expect(uploadCalled).toBe(true);
  });

  it('pushChanges sends image_url in POST /api/notes body when imageBlob present', async () => {
    dbMocks.notesGet.mockResolvedValue(MOCK_LOCAL_NOTE_IMAGE);
    dbMocks.syncQueueToArray.mockResolvedValue([MOCK_SYNC_QUEUE_IMAGE_ITEM]);

    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url === '/api/upload') {
        return Promise.resolve({ ok: true, json: async () => ({ url: IMAGE_UPLOAD_URL }) });
      }
      if (url === '/api/notes') {
        return Promise.resolve({ ok: true, json: async () => CREATED_SERVER_NOTE });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    }));

    const sm = await makeFreshSyncManager();
    await sm.pushChanges();

    const mockFetchFn = vi.mocked(global.fetch as ReturnType<typeof vi.fn>);
    const createCall = mockFetchFn.mock.calls.find((call) => call[0] === '/api/notes');
    expect(createCall).toBeDefined();
    const body = JSON.parse(createCall[1].body as string);
    expect(body.image_url).toBe(IMAGE_UPLOAD_URL);
  });

  // --- After successful push ---

  it('updates local note syncStatus to synced after successful push', async () => {
    const sm = await makeFreshSyncManager();
    await sm.pushChanges();

    expect(dbMocks.notesUpdate).toHaveBeenCalledWith(
      'local-id-1',
      expect.objectContaining({ syncStatus: 'synced' }),
    );
  });

  it('updates local note serverId after successful push', async () => {
    const sm = await makeFreshSyncManager();
    await sm.pushChanges();

    expect(dbMocks.notesUpdate).toHaveBeenCalledWith(
      'local-id-1',
      expect.objectContaining({ serverId: CREATED_SERVER_NOTE.id }),
    );
  });

  it('deletes the queue item after successful push', async () => {
    const sm = await makeFreshSyncManager();
    await sm.pushChanges();
    expect(dbMocks.syncQueueDelete).toHaveBeenCalledWith(1);
  });

  // --- Retry logic ---

  it('increments retryCount on failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network failure')));

    const sm = await makeFreshSyncManager();
    await sm.pushChanges();

    expect(dbMocks.syncQueueUpdate).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ retryCount: 1 }),
    );
  });

  it('moves to deadLetter after 5 failures (retryCount=4 → 5th run triggers dead letter)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network failure')));
    dbMocks.syncQueueToArray.mockResolvedValue([{ ...MOCK_SYNC_QUEUE_ITEM, retryCount: 4 }]);

    const sm = await makeFreshSyncManager();
    await sm.pushChanges();

    expect(dbMocks.deadLetterAdd).toHaveBeenCalled();
    expect(dbMocks.syncQueueDelete).toHaveBeenCalledWith(1);
  });
});

// ---------------------------------------------------------------------------
// pullChanges (B13)
// ---------------------------------------------------------------------------

describe('SyncManager — pullChanges (Task 4.4 — B13)', () => {
  beforeEach(() => {
    dbMocks.notesGet.mockResolvedValue(MOCK_LOCAL_NOTE_AUDIO);
    dbMocks.notesUpdate.mockResolvedValue(undefined);
    dbMocks.notesAdd.mockResolvedValue('new-local-id');
    dbMocks.notesDelete.mockResolvedValue(undefined);
    dbMocks.notesWhereFirst.mockResolvedValue(null); // no local match → add new
    dbMocks.metaGet.mockResolvedValue({ key: 'lastPull', value: LAST_PULL_EPOCH });
    dbMocks.metaPut.mockResolvedValue(undefined);

    setupDefaultFetch();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    Object.values(dbMocks).forEach((m) => m.mockClear());
  });

  it('pullChanges calls GET /api/sync/pull with since= timestamp', async () => {
    const sm = await makeFreshSyncManager();
    await sm.pullChanges();

    const mockFetchFn = vi.mocked(global.fetch as ReturnType<typeof vi.fn>);
    const pullCall = mockFetchFn.mock.calls.find(
      (call) => typeof call[0] === 'string' && (call[0] as string).includes('/api/sync/pull'),
    );
    expect(pullCall).toBeDefined();
    expect(pullCall![0] as string).toMatch(/since=/);
  });

  it('pullChanges uses the lastPull cursor from meta table', async () => {
    dbMocks.metaGet.mockResolvedValue({ key: 'lastPull', value: '2026-04-10T00:00:00Z' });

    const sm = await makeFreshSyncManager();
    await sm.pullChanges();

    const mockFetchFn = vi.mocked(global.fetch as ReturnType<typeof vi.fn>);
    const pullCall = mockFetchFn.mock.calls.find(
      (call) => typeof call[0] === 'string' && (call[0] as string).includes('/api/sync/pull'),
    );
    expect(pullCall).toBeDefined();
    // URL-encoded colon: 2026-04-10T00%3A00%3A00Z
    expect(pullCall![0] as string).toContain('2026-04-10');
  });

  it('adds new server notes that do not exist locally', async () => {
    const sm = await makeFreshSyncManager();
    await sm.pullChanges();

    expect(dbMocks.notesAdd).toHaveBeenCalled();
    const addArg = dbMocks.notesAdd.mock.calls[0][0];
    expect(addArg.syncStatus).toBe('synced');
  });

  it('updates lastPull cursor in meta table after pull', async () => {
    const sm = await makeFreshSyncManager();
    await sm.pullChanges();

    expect(dbMocks.metaPut).toHaveBeenCalledWith(
      expect.objectContaining({ key: 'lastPull', value: PULL_RESPONSE.server_time }),
    );
  });

  // --- Conflict detection ---

  it('flags syncStatus=conflict when local was updated after lastPull and is not synced', async () => {
    const lastPull = new Date('2026-04-10T00:00:00Z');
    dbMocks.metaGet.mockResolvedValue({ key: 'lastPull', value: lastPull.toISOString() });

    const conflictLocalNote = {
      localId: 'local-conflict-1',
      serverId: 'server-pulled-1',
      content: 'My local edits',
      syncStatus: 'pending', // has unsynced local edit
      processingStatus: 'enriched',
      updatedAt: new Date('2026-04-11T06:00:00Z'), // AFTER lastPull
      createdAt: new Date('2026-04-11T00:00:00Z'),
    };

    dbMocks.notesWhereFirst.mockResolvedValue(conflictLocalNote);

    const sm = await makeFreshSyncManager();
    await sm.pullChanges();

    expect(dbMocks.notesUpdate).toHaveBeenCalledWith(
      'local-conflict-1',
      expect.objectContaining({ syncStatus: 'conflict' }),
    );
  });

  it('stores conflictServerVersion when conflict detected', async () => {
    const lastPull = new Date('2026-04-10T00:00:00Z');
    dbMocks.metaGet.mockResolvedValue({ key: 'lastPull', value: lastPull.toISOString() });

    const conflictLocalNote = {
      localId: 'local-conflict-1',
      serverId: 'server-pulled-1',
      content: 'My local edits',
      syncStatus: 'pending',
      processingStatus: 'enriched',
      updatedAt: new Date('2026-04-11T06:00:00Z'),
      createdAt: new Date('2026-04-11T00:00:00Z'),
    };

    dbMocks.notesWhereFirst.mockResolvedValue(conflictLocalNote);

    const sm = await makeFreshSyncManager();
    await sm.pullChanges();

    expect(dbMocks.notesUpdate).toHaveBeenCalledWith(
      'local-conflict-1',
      expect.objectContaining({
        conflictServerVersion: PULL_RESPONSE.notes[0],
      }),
    );
  });

  it('updates (synced) local note when local.syncStatus=synced (no conflict)', async () => {
    const lastPull = new Date('2026-04-10T00:00:00Z');
    dbMocks.metaGet.mockResolvedValue({ key: 'lastPull', value: lastPull.toISOString() });

    const syncedLocalNote = {
      localId: 'local-synced-1',
      serverId: 'server-pulled-1',
      content: 'Synced content',
      syncStatus: 'synced', // already synced → no conflict
      processingStatus: 'enriched',
      updatedAt: new Date('2026-04-09T00:00:00Z'), // BEFORE lastPull
      createdAt: new Date('2026-04-09T00:00:00Z'),
    };

    dbMocks.notesWhereFirst.mockResolvedValue(syncedLocalNote);

    const sm = await makeFreshSyncManager();
    await sm.pullChanges();

    expect(dbMocks.notesUpdate).toHaveBeenCalledWith(
      'local-synced-1',
      expect.objectContaining({ syncStatus: 'synced' }),
    );
    // Should NOT be a conflict
    const updateArg = dbMocks.notesUpdate.mock.calls[0][1];
    expect(updateArg.conflictServerVersion).toBeUndefined();
  });

  it('handles deletions from server by removing local note', async () => {
    const pullWithDeletion = { ...PULL_RESPONSE, notes: [], deletions: ['server-deleted-id'] };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => pullWithDeletion,
    }));

    const deletedLocalNote = {
      localId: 'local-to-delete',
      serverId: 'server-deleted-id',
      syncStatus: 'synced',
    };
    dbMocks.notesWhereFirst.mockResolvedValue(deletedLocalNote);

    const sm = await makeFreshSyncManager();
    await sm.pullChanges();

    expect(dbMocks.notesDelete).toHaveBeenCalledWith('local-to-delete');
  });

  it('uses epoch as lastPull if no meta entry exists', async () => {
    dbMocks.metaGet.mockResolvedValue(undefined);

    const sm = await makeFreshSyncManager();
    await sm.pullChanges();

    const mockFetchFn = vi.mocked(global.fetch as ReturnType<typeof vi.fn>);
    const pullCall = mockFetchFn.mock.calls.find(
      (call) => typeof call[0] === 'string' && (call[0] as string).includes('/api/sync/pull'),
    );
    expect(pullCall).toBeDefined();
    expect(pullCall![0] as string).toContain('since=');
  });
});
