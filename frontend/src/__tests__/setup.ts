import '@testing-library/jest-dom';
import { indexedDB, IDBKeyRange } from 'fake-indexeddb';

// Polyfill IndexedDB for jsdom environment
Object.defineProperty(globalThis, 'indexedDB', {
  value: indexedDB,
  writable: true,
});

Object.defineProperty(globalThis, 'IDBKeyRange', {
  value: IDBKeyRange,
  writable: true,
});
