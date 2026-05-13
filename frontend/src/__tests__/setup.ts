import '@testing-library/jest-dom';
import { indexedDB, IDBKeyRange } from 'fake-indexeddb';
import { afterAll } from 'vitest';

// Polyfill IndexedDB for jsdom environment
Object.defineProperty(globalThis, 'indexedDB', {
  value: indexedDB,
  writable: true,
});

Object.defineProperty(globalThis, 'IDBKeyRange', {
  value: IDBKeyRange,
  writable: true,
});

// ---------------------------------------------------------------------------
// Force-close open Dexie/IndexedDB handles after all tests complete.
//
// Root cause: fake-indexeddb keeps event loop refs open even after all tests
// finish. When running the full suite, workers never exit, causing vitest's
// main process to wait indefinitely.
// ---------------------------------------------------------------------------
afterAll(async () => {
  try {
    const { db } = await import('../db');
    if (db.isOpen()) {
      db.close();
    }
  } catch {
    // ignore — db module may not be available in all test files
  }
});
