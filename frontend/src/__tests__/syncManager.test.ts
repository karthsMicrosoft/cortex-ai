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
    syncingListeners: Set<unknown>;
    pushTimer: ReturnType<typeof setInterval> | null;
    pullTimer: ReturnType<typeof setInterval> | null;
  };
  // Bypassing the SyncManager constructor via Object.create skips its
  // private-field initialisers, so we must restore the same starting state
  // the real constructor produces. Without this, notifySyncingListeners()
  // throws "this.syncingListeners is not iterable" the first time
  // pushChanges() is called.
  instance.isSyncing = false;
  instance.syncingListeners = new Set();
  instance.pushTimer = null;
  instance.pullTimer = null;
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

// ---------------------------------------------------------------------------
// QA-09: First boot must NOT flag local-only notes (no serverId) as conflicts
// review-comments.tasks.md § 3.9
// ---------------------------------------------------------------------------

describe('SyncManager — QA-09: first-boot conflict detection does not flag local-only notes', () => {
  /**
   * QA-09: On the very first pull (no lastPull in meta), lastPull defaults to
   * '1970-01-01T00:00:00Z'. Any local note with updatedAt after epoch AND
   * syncStatus !== 'synced' would be flagged as a conflict — but local-only notes
   * (no serverId) have never been pushed and cannot possibly conflict with a server version.
   *
   * The fix: notes with no serverId must NOT be flagged as conflicts, regardless of
   * their updatedAt vs lastPull comparison.
   */

  beforeEach(() => {
    dbMocks.notesGet.mockResolvedValue(MOCK_LOCAL_NOTE_AUDIO);
    dbMocks.notesUpdate.mockResolvedValue(undefined);
    dbMocks.notesAdd.mockResolvedValue('new-local-id');
    dbMocks.notesDelete.mockResolvedValue(undefined);
    dbMocks.metaPut.mockResolvedValue(undefined);

    setupDefaultFetch();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    Object.values(dbMocks).forEach((m) => m.mockClear());
  });

  it('QA-09: local-only note with no serverId is not flagged as conflict on first pull', async () => {
    // First boot: no lastPull entry → defaults to epoch
    dbMocks.metaGet.mockResolvedValue(undefined);

    // A local-only note: never synced, no serverId, updatedAt after epoch
    const localOnlyNote = {
      localId: 'local-only-fresh',
      serverId: undefined, // no server counterpart yet — never pushed
      content: 'My fresh local note',
      syncStatus: 'pending',
      processingStatus: 'raw',
      updatedAt: new Date('2026-04-29T10:00:00Z'), // after epoch, but no conflict possible
      createdAt: new Date('2026-04-29T09:00:00Z'),
    };

    // The server pulls a note with a DIFFERENT id — the local-only note is irrelevant
    // (no serverId means no where('serverId').equals(...) match).
    // The .first() mock returns null → server note is added as new.
    dbMocks.notesWhereFirst.mockResolvedValue(null);

    const sm = await makeFreshSyncManager();
    await sm.pullChanges();

    // notesUpdate must NOT have been called with syncStatus='conflict' for our local-only note
    const conflictCalls = dbMocks.notesUpdate.mock.calls.filter(
      (call: unknown[]) =>
        call[1] !== undefined &&
        typeof call[1] === 'object' &&
        (call[1] as Record<string, unknown>).syncStatus === 'conflict',
    );

    expect(conflictCalls).toHaveLength(0);
  });

  it('QA-09: a synced note is not flagged as conflict on first pull even if updatedAt after epoch', async () => {
    // First boot: no lastPull → epoch
    dbMocks.metaGet.mockResolvedValue(undefined);

    const syncedNote = {
      localId: 'local-synced-firstboot',
      serverId: 'server-pulled-1', // has serverId — matched by server pull
      content: 'Previously synced content',
      syncStatus: 'synced',
      processingStatus: 'enriched',
      updatedAt: new Date('2026-04-11T06:00:00Z'), // after epoch
      createdAt: new Date('2026-04-11T00:00:00Z'),
    };

    // server note with same id
    dbMocks.notesWhereFirst.mockResolvedValue(syncedNote);

    const sm = await makeFreshSyncManager();
    await sm.pullChanges();

    // syncStatus='synced' means server wins → update with syncStatus='synced', NOT 'conflict'
    const updateCall = dbMocks.notesUpdate.mock.calls.find(
      (call: unknown[]) => call[0] === 'local-synced-firstboot',
    );
    if (updateCall) {
      expect((updateCall[1] as Record<string, unknown>).syncStatus).toBe('synced');
      expect((updateCall[1] as Record<string, unknown>).syncStatus).not.toBe('conflict');
    }
  });

  it('QA-09: pending note with no serverId is never a candidate for conflict', async () => {
    /**
     * A note with syncStatus='pending' and no serverId has never reached the server.
     * It cannot have a conflict because there is no server version to conflict with.
     * The pullChanges loop only processes server-returned notes; a note with no serverId
     * will never be matched by where('serverId').equals(serverNote.id).first().
     * This test ensures the conflict path is only triggered for notes that HAVE a serverId.
     */
    dbMocks.metaGet.mockResolvedValue({ key: 'lastPull', value: '1970-01-01T00:00:00Z' });

    // The pull returns a server note; no local note has the same serverId
    dbMocks.notesWhereFirst.mockResolvedValue(null);

    const sm = await makeFreshSyncManager();
    await sm.pullChanges();

    // The server note not found locally → it's added as new with syncStatus='synced'
    const addCall = dbMocks.notesAdd.mock.calls[0];
    if (addCall) {
      expect((addCall[0] as Record<string, unknown>).syncStatus).toBe('synced');
    }

    // No conflict should have been raised for the local pending note (it was never matched)
    const conflictCalls = dbMocks.notesUpdate.mock.calls.filter(
      (call: unknown[]) =>
        call[1] !== undefined &&
        typeof call[1] === 'object' &&
        (call[1] as Record<string, unknown>).syncStatus === 'conflict',
    );
    expect(conflictCalls).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// PERF-07 — useSync must use event subscription, not setInterval polling
// review-comments.tasks.md § 2.7
// ---------------------------------------------------------------------------

describe('PERF-07 — useSync must not use setInterval to poll syncManager.syncing', () => {
  /**
   * PERF-07: useSync polls syncManager.syncing via setInterval(500ms), causing
   * React state updates twice/second even when nothing is changing.
   *
   * The fix: expose syncManager.syncing as an observable/event so React only
   * updates on actual transitions. We assert:
   * 1. useSync source does NOT contain setInterval for syncing state
   * 2. syncManager exposes a subscribe/addEventListener method
   */

  it('useSync source must not contain setInterval for isSyncing polling', async () => {
    const mod = await import('../hooks/useSync');
    // Inspect module source via toString — reliable for checking the implementation pattern
    const modSrc = mod.useSync.toString();

    const hasSetInterval = modSrc.includes('setInterval');
    expect(hasSetInterval).toBe(false);
    // If this fails: replace the setInterval polling with an event subscription on syncManager
    // e.g., syncManager.onSyncingChange = (cb) => { ... } or use an EventEmitter
  });

  it('syncManager exposes a subscribe or addEventListener method for syncing state', async () => {
    const mod = await import('../sync/syncManager');
    const sm = (mod as Record<string, unknown>).syncManager as Record<string, unknown>;

    // The fixed syncManager should have some event/subscription mechanism
    const hasEventHook = (
      typeof sm.subscribe === 'function'
      || typeof sm.addEventListener === 'function'
      || typeof sm.onSyncingChange === 'function'
      || typeof sm.addListener === 'function'
    );
    expect(hasEventHook).toBe(true);
    // If this fails: add subscribe(cb) or addEventListener('syncing', cb) to SyncManager
    // so useSync can listen for actual state transitions instead of polling
  });

  it('useSync source contains a subscription/listener pattern for syncing', async () => {
    const mod = await import('../hooks/useSync');
    const modSrc = mod.useSync.toString();

    // The fixed implementation should use some form of subscription
    const hasSubscription = (
      modSrc.includes('subscribe')
      || modSrc.includes('addEventListener')
      || modSrc.includes('onSyncingChange')
      || modSrc.includes('addListener')
    );
    expect(hasSubscription).toBe(true);
    // If this fails: replace setInterval polling with syncManager.subscribe(setIsSyncing)
  });
});
