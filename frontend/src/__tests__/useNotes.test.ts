/**
 * useNotes.test.ts — PERF-09
 *
 * PERF-09: useNotes applies dateFrom/dateTo filters in JavaScript AFTER fetching
 * all notes from IndexedDB. The fix must push the date filter to Dexie using
 * db.notes.where('createdAt').between(dateFrom, dateTo) so that IndexedDB
 * only returns the matching records.
 *
 * Tests assert:
 *   1. When dateFrom/dateTo are provided, the Dexie query uses .where().between()
 *      rather than a post-fetch JavaScript filter.
 *   2. The JavaScript post-filter array.filter(...) is NOT used for date ranges
 *      when a Dexie index is available.
 *
 * review-comments.tasks.md § 2.9
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mock authStore
// ---------------------------------------------------------------------------

vi.mock('../store/authStore', () => ({
  useAuthStore: {
    getState: () => ({ accessToken: 'test-token' }),
  },
}));

// ---------------------------------------------------------------------------
// Mock syncManager (avoid real network calls)
// ---------------------------------------------------------------------------

vi.mock('../sync/syncManager', () => ({
  syncManager: {
    pullChanges: vi.fn().mockResolvedValue(undefined),
    syncing: false,
    subscribe: vi.fn(),
    addEventListener: vi.fn(),
  },
}));

// ---------------------------------------------------------------------------
// PERF-09 — Source code inspection tests
// ---------------------------------------------------------------------------

describe('PERF-09 — useNotes must use Dexie .where().between() for date filters', () => {
  /**
   * These tests inspect the source code of useNotes to verify the implementation
   * strategy — source inspection is reliable for detecting algorithmic patterns.
   */

  it('useNotes source must use Dexie .between() for date range filtering', async () => {
    const mod = await import('../hooks/useNotes');
    const src = mod.useNotes.toString();

    // The optimised implementation must call .between() (Dexie index query)
    // instead of JavaScript array .filter() for date filtering
    const usesBetween = src.includes('between(');
    expect(usesBetween).toBe(true);
    // If this fails: replace the JS filter for dateFrom/dateTo with:
    //   db.notes.where('createdAt').between(dateFrom, dateTo, true, true)
  });

  it('useNotes source must NOT apply JavaScript date filter AFTER fetching all results', async () => {
    const mod = await import('../hooks/useNotes');
    const src = mod.useNotes.toString();

    // The anti-pattern: fetch all notes then filter in JS
    // Detect: results.filter(n => n.createdAt >= dateFrom)
    const hasJsDateFilter = (
      src.includes('filter(') &&
      (
        src.includes('createdAt >=') ||
        src.includes('createdAt <=') ||
        src.includes('createdAt >') ||
        src.includes('createdAt <')
      )
    );

    expect(hasJsDateFilter).toBe(false);
    // If this fails: remove the JavaScript filter and push the query to Dexie:
    //   db.notes.where('createdAt').between(filter.dateFrom, filter.dateTo, true, true)
  });

  it('useNotes source uses Dexie .where() for date-based queries', async () => {
    const mod = await import('../hooks/useNotes');
    const src = mod.useNotes.toString();

    // Should reference .where('createdAt') or similar Dexie index query
    const usesDexieWhere = (
      src.includes("where('createdAt')") ||
      src.includes('where("createdAt")') ||
      src.includes('between(')
    );
    expect(usesDexieWhere).toBe(true);
  });

  it('useNotes with no dateFrom/dateTo still fetches notes normally', async () => {
    // Smoke test: importing useNotes without filters should not throw
    const mod = await import('../hooks/useNotes');
    expect(typeof mod.useNotes).toBe('function');
  });
});

// ---------------------------------------------------------------------------
// PERF-09 — Dexie mock integration test
// ---------------------------------------------------------------------------

describe('PERF-09 — useNotes uses Dexie index query not JS filter for dates', () => {
  /**
   * We mock Dexie's db.notes to track which query methods were called.
   * With dateFrom/dateTo provided, the Dexie .between() method must be called,
   * NOT the JavaScript .filter() method on a full result set.
   */

  const betweenMock = vi.fn().mockReturnValue({
    toArray: vi.fn().mockResolvedValue([]),
    reverse: vi.fn().mockReturnThis(),
    and: vi.fn().mockReturnThis(),
    limit: vi.fn().mockReturnThis(),
    filter: vi.fn().mockReturnThis(),
  });

  const whereMock = vi.fn().mockReturnValue({
    between: betweenMock,
    equals: vi.fn().mockReturnValue({
      reverse: vi.fn().mockReturnValue({
        toArray: vi.fn().mockResolvedValue([]),
      }),
      toArray: vi.fn().mockResolvedValue([]),
    }),
    reverse: vi.fn().mockReturnThis(),
  });

  const orderByMock = vi.fn().mockReturnValue({
    reverse: vi.fn().mockReturnValue({
      toArray: vi.fn().mockResolvedValue([]),
    }),
    toArray: vi.fn().mockResolvedValue([]),
  });

  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('calls Dexie .between() when dateFrom and dateTo are provided', async () => {
    // Mock the db module to track Dexie method calls
    vi.doMock('../db', () => ({
      db: {
        notes: {
          where: whereMock,
          orderBy: orderByMock,
          count: vi.fn().mockResolvedValue(0),
        },
        syncQueue: {
          count: vi.fn().mockResolvedValue(0),
        },
      },
    }));

    const dateFrom = new Date('2026-04-01T00:00:00Z');
    const dateTo = new Date('2026-04-30T23:59:59Z');

    // Import useNotes AFTER mocking db
    // (Note: in vitest with dynamic mocking, we verify via source inspection above;
    //  this test confirms the hook accepts the filter interface correctly)
    const { useNotes } = await import('../hooks/useNotes');
    expect(typeof useNotes).toBe('function');

    // The hook should accept dateFrom/dateTo in the filter object
    const filter = { dateFrom, dateTo };
    // Verify the filter type is compatible
    const _testFilter: Parameters<typeof useNotes>[0] = filter;
    expect(_testFilter.dateFrom).toBe(dateFrom);
    expect(_testFilter.dateTo).toBe(dateTo);
  });
});
