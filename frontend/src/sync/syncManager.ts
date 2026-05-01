import { db } from '../db';
import type { LocalNote, SyncQueue } from '../db';
import { useAuthStore } from '../store/authStore';
import { apiUrl } from '../api/client';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_RETRIES = 5;
const PUSH_POLL_INTERVAL_MS = 30_000; // 30 s
const PULL_POLL_INTERVAL_MS = 60_000; // 60 s

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NoteCreatePayload {
  content: string;
  source_type: string;
  audio_url?: string;
  image_url?: string;
  client_id: string;
  tags?: string[];
  category?: string;
}

interface NoteOut {
  id: string;
  content: string;
  processing_status: string;
  updated_at: string;
  [key: string]: unknown;
}

interface PullResponse {
  notes: NoteOut[];
  deletions: string[];
  server_time: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getToken(): string | null {
  return useAuthStore.getState().accessToken;
}

async function uploadBlob(blob: Blob, mimeType: string): Promise<string> {
  const token = getToken();
  if (!token) throw new Error('Not authenticated');

  const formData = new FormData();
  const ext = mimeType.startsWith('image') ? 'jpg' : 'webm';
  formData.append('file', blob, `upload-${Date.now()}.${ext}`);

  const res = await fetch(apiUrl('/api/upload'), {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (!res.ok) throw new Error(`Blob upload failed: ${res.status}`);
  const json = (await res.json()) as { url: string };
  return json.url;
}

async function createNoteOnServer(payload: NoteCreatePayload): Promise<NoteOut> {
  const token = getToken();
  if (!token) throw new Error('Not authenticated');

  const res = await fetch(apiUrl('/api/notes'), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) throw new Error(`Note create failed: ${res.status}`);
  return res.json() as Promise<NoteOut>;
}

async function updateNoteOnServer(id: string, payload: Record<string, unknown>): Promise<NoteOut> {
  const token = getToken();
  if (!token) throw new Error('Not authenticated');

  const res = await fetch(apiUrl(`/api/notes/${id}`), {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) throw new Error(`Note update failed: ${res.status}`);
  return res.json() as Promise<NoteOut>;
}

async function deleteNoteOnServer(id: string): Promise<void> {
  const token = getToken();
  if (!token) throw new Error('Not authenticated');

  const res = await fetch(apiUrl(`/api/notes/${id}`), {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) throw new Error(`Note delete failed: ${res.status}`);
}

function mapServerToLocal(
  serverNote: NoteOut,
  opts?: { keepLocalContent?: string },
): Partial<LocalNote> {
  return {
    serverId: serverNote.id,
    content: opts?.keepLocalContent ?? String(serverNote.content ?? ''),
    processingStatus: (serverNote.processing_status as LocalNote['processingStatus']) ?? 'raw',
    updatedAt: new Date(String(serverNote.updated_at)),
    // Other fields from server can be merged as needed
  };
}

// ---------------------------------------------------------------------------
// SyncManager — singleton
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// SyncingListener — callback type for PERF-07 event emitter pattern
// ---------------------------------------------------------------------------

type SyncingListener = (syncing: boolean) => void;

export class SyncManager {
  private static instance: SyncManager;
  private isSyncing = false;
  private pushTimer: ReturnType<typeof setInterval> | null = null;
  private pullTimer: ReturnType<typeof setInterval> | null = null;

  /** PERF-07: event listeners notified on every isSyncing state change */
  private syncingListeners: Set<SyncingListener> = new Set();

  private constructor() {}

  static getInstance(): SyncManager {
    if (!SyncManager.instance) {
      SyncManager.instance = new SyncManager();
    }
    return SyncManager.instance;
  }

  // --------------------------------------------------------------------------
  // Lifecycle
  // --------------------------------------------------------------------------

  /** Call once after auth to wire up event listeners and start polling. */
  async start(): Promise<void> {
    // QA-09 fix: on first boot (no lastPull entry), initialize to now so the
    // first pull only marks conflicts on notes modified AFTER app installation.
    // Without this the epoch default causes every pending local note (no serverId)
    // to be incorrectly flagged as a conflict on first pull.
    const existing = await db.meta.get('lastPull');
    if (!existing) {
      await db.meta.put({ key: 'lastPull', value: new Date().toISOString() });
    }

    window.addEventListener('online', () => void this.pushChanges());
    window.addEventListener('online', () => void this.pullChanges());

    this.pushTimer = setInterval(() => void this.pushChanges(), PUSH_POLL_INTERVAL_MS);
    this.pullTimer = setInterval(() => void this.pullChanges(), PULL_POLL_INTERVAL_MS);

    // Initial sync on boot
    void this.pushChanges();
    void this.pullChanges();
  }

  stop(): void {
    if (this.pushTimer) clearInterval(this.pushTimer);
    if (this.pullTimer) clearInterval(this.pullTimer);
    this.pushTimer = null;
    this.pullTimer = null;
  }

  // --------------------------------------------------------------------------
  // Push
  // --------------------------------------------------------------------------

  // --------------------------------------------------------------------------
  // PERF-07 — event emitter API for syncing state
  // --------------------------------------------------------------------------

  /**
   * Subscribe to syncing state changes.  Listener is called immediately with
   * the current value, then on every subsequent transition.
   * Returns an unsubscribe function.
   */
  onSyncingChange(listener: SyncingListener): () => void {
    this.syncingListeners.add(listener);
    listener(this.isSyncing); // fire immediately with current state
    return () => {
      this.syncingListeners.delete(listener);
    };
  }

  private notifySyncingListeners(syncing: boolean): void {
    for (const listener of this.syncingListeners) {
      listener(syncing);
    }
  }

  async pushChanges(): Promise<void> {
    if (this.isSyncing || !navigator.onLine || !getToken()) return;
    this.isSyncing = true;
    this.notifySyncingListeners(true);

    try {
      // FIFO drain — order by id (auto-increment == insertion order)
      const queue = await db.syncQueue.orderBy('id').toArray();
      for (const op of queue) {
        await this.pushOne(op);
      }
    } finally {
      this.isSyncing = false;
      this.notifySyncingListeners(false);
    }
  }

  private async pushOne(op: SyncQueue): Promise<void> {
    try {
      if (op.operation === 'create') {
        await this.pushCreate(op);
      } else if (op.operation === 'update') {
        await this.pushUpdate(op);
      } else if (op.operation === 'delete') {
        await this.pushDelete(op);
      }
    } catch {
      // Bump retry count
      const newRetry = (op.retryCount ?? 0) + 1;
      if (newRetry >= MAX_RETRIES) {
        // Move to dead-letter (critique mitigation #2)
        await db.deadLetter.add({
          operation: op.operation,
          entityType: op.entityType,
          entityId: op.entityId,
          payload: op.payload,
          timestamp: op.timestamp,
          retryCount: newRetry,
          failedAt: new Date(),
        });
        if (op.id !== undefined) await db.syncQueue.delete(op.id);
      } else {
        if (op.id !== undefined) {
          await db.syncQueue.update(op.id, { retryCount: newRetry });
        }
      }
    }
  }

  private async pushCreate(op: SyncQueue): Promise<void> {
    const localId = op.entityId;
    const note = await db.notes.get(localId);
    if (!note) {
      // Note was deleted locally before sync — just remove the queue item
      if (op.id !== undefined) await db.syncQueue.delete(op.id);
      return;
    }

    let audioUrl: string | undefined;
    let imageUrl: string | undefined;

    // B11: image branch — upload imageBlob first
    if (note.imageBlob) {
      imageUrl = await uploadBlob(note.imageBlob, note.imageBlob.type || 'image/jpeg');
    }

    // Audio branch
    if (note.audioBlob) {
      audioUrl = await uploadBlob(note.audioBlob, 'audio/webm');
    }

    const created = await createNoteOnServer({
      content: note.content,
      source_type: note.sourceType,
      audio_url: audioUrl,
      image_url: imageUrl,
      client_id: note.localId,
      tags: note.tags,
      category: note.category,
    });

    await db.notes.update(localId, {
      serverId: created.id,
      syncStatus: 'synced',
      processingStatus: (created.processing_status as LocalNote['processingStatus']) ?? 'raw',
      audioBlob: undefined,
      imageBlob: undefined,
      updatedAt: new Date(),
    });

    if (op.id !== undefined) await db.syncQueue.delete(op.id);
  }

  private async pushUpdate(op: SyncQueue): Promise<void> {
    const localId = op.entityId;
    const note = await db.notes.get(localId);
    if (!note?.serverId) {
      if (op.id !== undefined) await db.syncQueue.delete(op.id);
      return;
    }

    await updateNoteOnServer(note.serverId, op.payload);
    await db.notes.update(localId, { syncStatus: 'synced', updatedAt: new Date() });

    if (op.id !== undefined) await db.syncQueue.delete(op.id);
  }

  private async pushDelete(op: SyncQueue): Promise<void> {
    const serverId = op.payload.serverId as string | undefined;
    if (serverId) {
      await deleteNoteOnServer(serverId);
    }
    if (op.id !== undefined) await db.syncQueue.delete(op.id);
  }

  // --------------------------------------------------------------------------
  // Pull (B13)
  // --------------------------------------------------------------------------

  async pullChanges(): Promise<void> {
    if (!navigator.onLine || !getToken()) return;

    const token = getToken();
    if (!token) return;

    const metaEntry = await db.meta.get('lastPull');
    const lastPull = metaEntry?.value ?? '1970-01-01T00:00:00Z';

    const res = await fetch(apiUrl(`/api/sync/pull?since=${encodeURIComponent(lastPull)}`), {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!res.ok) return; // network error or 4xx — skip silently

    const { notes, deletions, server_time } = (await res.json()) as PullResponse;

    await db.transaction('rw', [db.notes, db.meta], async () => {
      for (const serverNote of notes) {
        const local = await db.notes.where('serverId').equals(serverNote.id).first();

        if (!local) {
          // New note from server — add locally
          await db.notes.add({
            localId: serverNote.id, // use serverId as localId for server-originated notes
            ...mapServerToLocal(serverNote),
            serverId: serverNote.id,
            sourceType: 'text',
            category: 'Ideas',
            tags: [],
            syncStatus: 'synced',
            processingStatus:
              (serverNote.processing_status as LocalNote['processingStatus']) ?? 'raw',
            createdAt: new Date(String(serverNote['created_at'] ?? Date.now())),
            updatedAt: new Date(String(serverNote.updated_at ?? Date.now())),
          } as LocalNote);
        } else if (
          local.updatedAt > new Date(lastPull) &&
          local.syncStatus !== 'synced'
        ) {
          // Conflict: local was edited after lastPull and not yet synced
          await db.notes.update(local.localId, {
            ...mapServerToLocal(serverNote, { keepLocalContent: local.content }),
            syncStatus: 'conflict',
            conflictServerVersion: serverNote,
          });
        } else {
          // Server wins — overwrite local
          await db.notes.update(local.localId, {
            ...mapServerToLocal(serverNote),
            syncStatus: 'synced',
          });
        }
      }

      // Handle deletions
      for (const deletedId of deletions) {
        const local = await db.notes.where('serverId').equals(deletedId).first();
        if (local) await db.notes.delete(local.localId);
      }

      // Advance lastPull cursor
      await db.meta.put({ key: 'lastPull', value: server_time });
    });
  }

  // --------------------------------------------------------------------------
  // Accessors
  // --------------------------------------------------------------------------

  get syncing(): boolean {
    return this.isSyncing;
  }
}

// ---------------------------------------------------------------------------
// Singleton export
// ---------------------------------------------------------------------------
export const syncManager = SyncManager.getInstance();
