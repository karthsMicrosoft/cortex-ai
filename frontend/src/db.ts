import Dexie, { type Table } from 'dexie';

// ---------------------------------------------------------------------------
// Interfaces — per design § "IndexedDB schema" and spec § 2.3
// ---------------------------------------------------------------------------

export type SourceType = 'voice' | 'text' | 'image';
export type Category = 'Music' | 'Fitness' | 'Journal' | 'Ideas' | 'Spiritual' | 'Learning';
export type SyncStatus = 'pending' | 'synced' | 'conflict';
export type ProcessingStatus = 'raw' | 'transcribed' | 'processed' | 'enriched' | 'failed';
export type SyncOperation = 'create' | 'update' | 'delete';
export type DeadlinePriority = 1 | 2 | 3;
export type DeadlineRecurring = 'daily' | 'weekly' | 'monthly';

export interface LocalNote {
  /** Auto-assigned UUID — primary key in IndexedDB */
  localId: string;
  /** Server-side UUID — set after successful sync */
  serverId?: string;
  content: string;
  rawTranscription?: string;
  sourceType: SourceType;
  category: Category;
  /** Audio blob for offline voice notes (uploaded on sync) */
  audioBlob?: Blob;
  /** Image blob for offline image notes (uploaded on sync) */
  imageBlob?: Blob;
  tags: string[];
  mood?: string;
  due_at?: string | null;
  done_at?: string | null;
  priority?: DeadlinePriority | null;
  recurring?: DeadlineRecurring | null;
  reminder_sent_at?: string | null;
  syncStatus: SyncStatus;
  processingStatus: ProcessingStatus;
  due_at_hint?: string;
  priority_hint?: DeadlinePriority;
  recurring_hint?: DeadlineRecurring;
  /** Frozen server payload for conflict resolution (set when syncStatus='conflict') */
  conflictServerVersion?: unknown;
  createdAt: Date;
  updatedAt: Date;
}

export interface SyncQueue {
  /** Auto-incremented by Dexie (++id) */
  id?: number;
  operation: SyncOperation;
  entityType: string;
  entityId: string;
  payload: Record<string, unknown>;
  timestamp: Date;
  retryCount: number;
}

/** Dead-letter queue — items that failed > 5 times (critique mitigation #2) */
export interface DeadLetter {
  id?: number;
  operation: SyncOperation;
  entityType: string;
  entityId: string;
  payload: Record<string, unknown>;
  timestamp: Date;
  retryCount: number;
  failedAt: Date;
}

/** Meta key-value store — persists lastPull cursor etc. */
export interface MetaEntry {
  key: string;
  value: string;
}

/**
 * Phase 5 / PR 5.1 — Shared inbox.
 *
 * Stores share-target payloads received while the user is logged out. The
 * SessionGate drains this table once the user authenticates (either via
 * silent refresh on boot or a fresh login).
 */
export interface SharedInboxEntry {
  /** Auto-incremented by Dexie (++id) */
  id?: number;
  title?: string;
  text?: string;
  url?: string;
  /** ISO 8601 timestamp */
  created_at: string;
}

// ---------------------------------------------------------------------------
// CortexDB — Dexie database class
// ---------------------------------------------------------------------------

export class CortexDB extends Dexie {
  notes!: Table<LocalNote, string>;
  syncQueue!: Table<SyncQueue, number>;
  deadLetter!: Table<DeadLetter, number>;
  meta!: Table<MetaEntry, string>;
  shared_inbox!: Table<SharedInboxEntry, number>;

  constructor() {
    super('cortex-db');

    this.version(1).stores({
      // Primary key: localId; indexes: serverId, sourceType, category, syncStatus, createdAt
      notes: 'localId, serverId, sourceType, category, syncStatus, createdAt',
      // Auto-increment primary key (++id); indexes: operation, entityType, timestamp
      syncQueue: '++id, operation, entityType, timestamp',
    });

    // v2 adds deadLetter and meta tables (B13 pull flow + critique mitigation #2)
    this.version(2).stores({
      notes: 'localId, serverId, sourceType, category, syncStatus, createdAt',
      syncQueue: '++id, operation, entityType, timestamp',
      deadLetter: '++id, operation, entityType, timestamp',
      meta: 'key',
    });

    // v3 (Phase 5 / PR 5.1) adds shared_inbox for the PWA share-target stash.
    // Schema-only migration — no per-row transform required.
    this.version(3).stores({
      notes: 'localId, serverId, sourceType, category, syncStatus, createdAt',
      syncQueue: '++id, operation, entityType, timestamp',
      deadLetter: '++id, operation, entityType, timestamp',
      meta: 'key',
      shared_inbox: '++id, created_at',
    });
  }
}

// ---------------------------------------------------------------------------
// Singleton export
// ---------------------------------------------------------------------------
export const db = new CortexDB();
