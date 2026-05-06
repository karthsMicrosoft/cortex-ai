/**
 * Task 3 (IndexedDB / Dexie schema) — TDD red
 *
 * Tests that db.ts exports:
 *   - LocalNote interface (exact fields per design § "IndexedDB schema")
 *   - SyncQueue interface
 *   - CortexDB extends Dexie with notes + syncQueue tables
 *   - Singleton `db` instance
 *   - Correct Dexie store indexes (notes and syncQueue)
 *
 * Deps needed: dexie, fake-indexeddb
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';

// We import the module under test. If the file doesn't exist yet this import
// will fail at compile/load time — that is the desired RED state.
import { db, CortexDB } from '../db';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Return the raw Dexie store schema string for a given table name */
function tableSchema(instance: CortexDB, tableName: string): string {
  // Dexie exposes schema on its internal `_dbSchema` property at runtime.
  // At test time we verify via the public `tables` array.
  const table = instance.tables.find((t) => t.name === tableName);
  if (!table) return '';
  // schema.primKey + indexes are available on table.schema
  const schema = (table as any).schema;
  const parts: string[] = [schema.primKey.src ?? schema.primKey.name];
  for (const idx of schema.indexes) {
    parts.push(idx.src ?? idx.name);
  }
  return parts.join(', ');
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CortexDB — Dexie schema (Task 3)', () => {
  it('exports a singleton db instance of CortexDB', () => {
    expect(db).toBeInstanceOf(CortexDB);
  });

  it('db name is "cortex-db"', () => {
    expect(db.name).toBe('cortex-db');
  });

  it('has a `notes` table', () => {
    const tableNames = db.tables.map((t) => t.name);
    expect(tableNames).toContain('notes');
  });

  it('has a `syncQueue` table', () => {
    const tableNames = db.tables.map((t) => t.name);
    expect(tableNames).toContain('syncQueue');
  });

  it('notes table primary key is localId', () => {
    const table = db.tables.find((t) => t.name === 'notes')!;
    const schema = (table as any).schema;
    expect(schema.primKey.name).toBe('localId');
  });

  it('notes table has required indexes: serverId, sourceType, category, syncStatus, createdAt', () => {
    const table = db.tables.find((t) => t.name === 'notes')!;
    const schema = (table as any).schema;
    const indexNames: string[] = schema.indexes.map((idx: any) => idx.name);
    expect(indexNames).toContain('serverId');
    expect(indexNames).toContain('sourceType');
    expect(indexNames).toContain('category');
    expect(indexNames).toContain('syncStatus');
    expect(indexNames).toContain('createdAt');
  });

  it('syncQueue table uses auto-increment primary key (++id)', () => {
    const table = db.tables.find((t) => t.name === 'syncQueue')!;
    const schema = (table as any).schema;
    expect(schema.primKey.auto).toBe(true);
    expect(schema.primKey.name).toBe('id');
  });

  it('syncQueue table has indexes: operation, entityType, timestamp', () => {
    const table = db.tables.find((t) => t.name === 'syncQueue')!;
    const schema = (table as any).schema;
    const indexNames: string[] = schema.indexes.map((idx: any) => idx.name);
    expect(indexNames).toContain('operation');
    expect(indexNames).toContain('entityType');
    expect(indexNames).toContain('timestamp');
  });
});

// ---------------------------------------------------------------------------
// LocalNote interface shape — verified by creating typed objects
// ---------------------------------------------------------------------------
describe('LocalNote interface shape', () => {
  it('accepts a valid LocalNote object with all required fields', () => {
    // This is a compile-time check expressed at runtime.
    // If the interface doesn't exist / has wrong fields, tsc (run by vite) fails.
    const note: import('../db').LocalNote = {
      localId: 'abc-123',
      content: 'Test note content',
      sourceType: 'text',
      category: 'Ideas',
      tags: [],
      syncStatus: 'pending',
      processingStatus: 'raw',
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    expect(note.localId).toBe('abc-123');
    expect(note.sourceType).toBe('text');
    expect(note.syncStatus).toBe('pending');
    expect(note.processingStatus).toBe('raw');
  });

  it('accepts optional fields on LocalNote', () => {
    const note: import('../db').LocalNote = {
      localId: 'def-456',
      serverId: 'server-uuid-1',
      content: 'Voice note',
      rawTranscription: 'raw transcript here',
      sourceType: 'voice',
      category: 'Music',
      audioBlob: new Blob(['audio'], { type: 'audio/webm' }),
      imageBlob: undefined,
      tags: ['music', 'idea'],
      mood: 'creative',
      syncStatus: 'synced',
      processingStatus: 'enriched',
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    expect(note.serverId).toBe('server-uuid-1');
    expect(note.rawTranscription).toBe('raw transcript here');
    expect(note.mood).toBe('creative');
  });
});

// ---------------------------------------------------------------------------
// SyncQueue interface shape
// ---------------------------------------------------------------------------
describe('SyncQueue interface shape', () => {
  it('accepts a valid SyncQueue object', () => {
    const op: import('../db').SyncQueue = {
      operation: 'create',
      entityType: 'note',
      entityId: 'abc-123',
      payload: { content: 'hello' },
      timestamp: new Date(),
      retryCount: 0,
    };
    expect(op.operation).toBe('create');
    expect(op.entityType).toBe('note');
    expect(op.retryCount).toBe(0);
  });

  it('allows id to be optional (auto-set by Dexie)', () => {
    const op: import('../db').SyncQueue = {
      operation: 'delete',
      entityType: 'note',
      entityId: 'xyz',
      payload: {},
      timestamp: new Date(),
      retryCount: 0,
      // id omitted — Dexie assigns it
    };
    expect(op.id).toBeUndefined();
  });
});
