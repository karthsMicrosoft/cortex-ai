import Dexie, { type Table } from 'dexie';

// ---------------------------------------------------------------------------
// Interfaces — per design § "IndexedDB schema" and spec § 2.3
// ---------------------------------------------------------------------------

export type SourceType = 'voice' | 'text' | 'image';
export type Category = 'Music' | 'Fitness' | 'Journal' | 'Ideas' | 'Spiritual' | 'Learning';
export type SyncStatus = 'pending' | 'synced' | 'conflict';
export type ProcessingStatus = 'raw' | 'transcribed' | 'processed' | 'enriched' | 'failed';
export type SyncOperation = 'create' | 'update' | 'delete';

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
  syncStatus: SyncStatus;
  processingStatus: ProcessingStatus;
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

// ---------------------------------------------------------------------------
// CortexDB — Dexie database class
// ---------------------------------------------------------------------------

export class CortexDB extends Dexie {
  notes!: Table<LocalNote, string>;
  syncQueue!: Table<SyncQueue, number>;
  deadLetter!: Table<DeadLetter, number>;
  meta!: Table<MetaEntry, string>;

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
  }
}

// ---------------------------------------------------------------------------
// Singleton export
// ---------------------------------------------------------------------------
export const db = new CortexDB();
