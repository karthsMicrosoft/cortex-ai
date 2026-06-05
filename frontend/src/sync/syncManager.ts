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
  due_at_hint?: string;
  priority_hint?: 1 | 2 | 3;
  recurring_hint?: 'daily' | 'weekly' | 'monthly';
}

interface NoteOut {
  id: string;
  content: string;
  processing_status: string;
  updated_at: string;
  due_at?: string | null;
  done_at?: string | null;
  priority?: 1 | 2 | 3 | null;
  recurring?: 'daily' | 'weekly' | 'monthly' | null;
  reminder_sent_at?: string | null;
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
    credentials: 'include',
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
    credentials: 'include',
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
    credentials: 'include',
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
    credentials: 'include',
  });

  if (!res.ok) throw new Error(`Note delete failed: ${res.status}`);
}

async function getNoteOnServer(id: string): Promise<NoteOut> {
  const token = getToken();
  if (!token) throw new Error('Not authenticated');
  const res = await fetch(apiUrl(`/api/notes/${id}`), {
    headers: { Authorization: `Bearer ${token}` },
    credentials: 'include',
  });
  if (!res.ok) throw new Error(`Note fetch failed: ${res.status}`);
  return res.json() as Promise<NoteOut>;
}

/**
 * After a freshly-created note syncs, the AI pipeline (Stage 1 + Stage 2)
 * runs server-side for ~5–15s. Poll a few times so the local row gets the
 * enriched category/tags/mood/raw_transcription without waiting for the
 * full 60s pull tick. Bug 11 fix.
 */
async function scheduleEnrichmentRefetch(localId: string, serverId: string): Promise<void> {
  const delays = [3_000, 6_000, 12_000, 25_000]; // up to 46s window
  for (const delay of delays) {
    await new Promise((r) => setTimeout(r, delay));
    try {
      const fresh = await getNoteOnServer(serverId);
      await db.notes.update(localId, mapServerToLocal(fresh));
      if (fresh.processing_status === 'enriched' || fresh.processing_status === 'failed') {
        return;
      }
    } catch {
      // Ignore individual failures — next 60s pull will catch up.
    }
  }
}

function mapServerToLocal(
  serverNote: NoteOut,
  opts?: { keepLocalContent?: string },
): Partial<LocalNote> {
  // 2026-05-01 fix (bug 11): merge ALL the AI-enriched fields from the server
  // back into the local row. Previously this only updated content + status +
  // updatedAt, so the Library card kept showing the default 'Ideas' category
  // and empty tags even after Stage 2 ran on the backend.
  const tags = Array.isArray(serverNote.tags)
    ? (serverNote.tags as string[])
    : undefined;
  const merged: Partial<LocalNote> = {
    serverId: serverNote.id,
    content: opts?.keepLocalContent ?? String(serverNote.content ?? ''),
    processingStatus:
      (serverNote.processing_status as LocalNote['processingStatus']) ?? 'raw',
    syncStatus: 'synced',
    updatedAt: new Date(String(serverNote.updated_at)),
  };
  if (typeof serverNote.category === 'string') {
    merged.category = serverNote.category as LocalNote['category'];
  }
  if (typeof serverNote.raw_transcription === 'string') {
    merged.rawTranscription = serverNote.raw_transcription;
  }
  if (tags) merged.tags = tags;
  if (typeof serverNote.mood === 'string') merged.mood = serverNote.mood;
  if (serverNote.due_at !== undefined) merged.due_at = serverNote.due_at;
  if (serverNote.done_at !== undefined) merged.done_at = serverNote.done_at;
  if (serverNote.priority !== undefined) merged.priority = serverNote.priority;
  if (serverNote.recurring !== undefined) merged.recurring = serverNote.recurring;
  if (serverNote.reminder_sent_at !== undefined) {
    merged.reminder_sent_at = serverNote.reminder_sent_at;
  }
  return merged;
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
    // Bug 17 fix (2026-05-01): on first boot (no lastPull entry) we MUST start
    // from epoch — otherwise a fresh browser / incognito session asks the
    // server for "notes since now" and never sees the user's existing
    // history. The earlier QA-09 seed-to-now was overcorrection: the
    // conflict-detection branch in pullChanges() only fires for local notes
    // that already have a matching serverId (i.e. previously synced), so
    // brand-new local-only notes can never be wrongly flagged as conflicts
    // by an epoch baseline. See syncManager.test.ts § QA-09.
    //
    // Additionally, MIGRATE existing browsers that were stuck with a "now"
    // seed from the buggy build: if the local DB has zero notes with
    // serverIds, no successful pull has ever happened — reset lastPull to
    // epoch so the next pull retrieves the user's full history. This is
    // safe (the conflict path is gated on serverId-match, so non-empty
    // local-only notes don't get flagged).
    const existing = await db.meta.get('lastPull');
    const seenServerNote = await db.notes
      .filter((n) => n.serverId !== undefined && n.serverId !== null)
      .first();
    if (!existing || !seenServerNote) {
      await db.meta.put({ key: 'lastPull', value: '1970-01-01T00:00:00Z' });
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

    // Bug 21 fix: voice notes that went through the /api/voice/upload fallback
    // path are already synced (syncStatus='synced', serverId set). Pushing them
    // again via POST /api/notes creates a duplicate server-side row.
    // The fallback path removes the queue item itself — but if pushChanges()
    // races ahead before the fallback resolves, the queue item is still visible.
    // Skip it here; the fallback cleanup or the next push cycle will tidy up.
    if (note.syncStatus === 'synced' && note.serverId) {
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
      ...(note.due_at_hint ? { due_at_hint: note.due_at_hint } : {}),
      ...(note.priority_hint ? { priority_hint: note.priority_hint } : {}),
      ...(note.recurring_hint ? { recurring_hint: note.recurring_hint } : {}),
    });

    // Immediately merge whatever the server returned (status will be 'raw' or
    // 'transcribed' here — Stage 2 enrichment fires asynchronously).
    await db.notes.update(localId, {
      ...mapServerToLocal(created),
      audioBlob: undefined,
      imageBlob: undefined,
    });

    if (op.id !== undefined) await db.syncQueue.delete(op.id);

    // Schedule a delayed re-fetch so we can pick up the AI-enriched
    // category/tags/mood once the backend pipeline finishes (~5–15s typical).
    // Without this the Library card stays on the default 'Ideas' label until
    // the next 60s poll tick.
    void scheduleEnrichmentRefetch(localId, created.id);
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
      credentials: 'include',
    });

    if (!res.ok) return; // network error or 4xx — skip silently

    const { notes, deletions, server_time } = (await res.json()) as PullResponse;

    await db.transaction('rw', [db.notes, db.meta], async () => {
      for (const serverNote of notes) {
        const local = await db.notes.where('serverId').equals(serverNote.id).first();

        if (!local) {
          // New note from server — add locally.
          // mapServerToLocal is spread LAST so AI-enriched fields (category, tags, mood)
          // from the server win over any defaults. Bug 24: placing category:'Ideas' after
          // the spread was overwriting the AI-assigned category on receiving browsers.
          const mapped = mapServerToLocal(serverNote);
          await db.notes.add({
            localId: serverNote.id, // use serverId as localId for server-originated notes
            serverId: serverNote.id,
            sourceType: (serverNote['source_type'] as LocalNote['sourceType']) ?? 'text',
            category: 'Ideas',
            tags: [],
            syncStatus: 'synced',
            processingStatus:
              (serverNote.processing_status as LocalNote['processingStatus']) ?? 'raw',
            createdAt: new Date(String(serverNote['created_at'] ?? Date.now())),
            updatedAt: new Date(String(serverNote.updated_at ?? Date.now())),
            ...mapped,
          } as LocalNote);
          // Bug 24 follow-up: if the note isn't enriched yet on the receiving browser,
          // schedule a re-fetch so category/tags update within ~10s rather than waiting
          // for the full 60s pull tick.
          if (
            serverNote.processing_status === 'raw' ||
            serverNote.processing_status === 'transcribed' ||
            serverNote.processing_status === 'processed'
          ) {
            void scheduleEnrichmentRefetch(serverNote.id, serverNote.id);
          }
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
