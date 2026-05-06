/**
 * InsightsPage.test.tsx - Task 5.1 (Insights UI)
 *
 * 2026-05-06: Tests for the daily/weekly summary cards were removed when
 * the cron functionality (and the underlying endpoints) were dropped.
 * This file now only covers the surviving Recurring Patterns surface.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mock authStore
// ---------------------------------------------------------------------------

const mockAuthState = { accessToken: 'test-token', user: { id: 'user-1', email: 'test@example.com', display_name: 'Test User' } };
const mockUseAuthStore = Object.assign(
  (selector: (s: typeof mockAuthState) => unknown) => selector(mockAuthState),
  { getState: () => mockAuthState, subscribe: vi.fn(), setState: vi.fn() },
);
vi.mock('../store/authStore', () => ({ useAuthStore: mockUseAuthStore }));

// ---------------------------------------------------------------------------
// Mock API responses
// ---------------------------------------------------------------------------

const MOCK_PATTERNS = {
  patterns: [
    { theme: 'Music Practice', evidence_note_ids: ['note-1', 'note-2'] },
    { theme: 'Morning Routine', evidence_note_ids: ['note-3'] },
  ],
};

const MOCK_EMPTY_PATTERNS = { patterns: [] };

// ---------------------------------------------------------------------------
// Mock fetch
// ---------------------------------------------------------------------------

function setupFetchMocks(overrides: Record<string, unknown> = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (url: string) => {
      if (url.includes('/api/insights/patterns')) {
        return {
          ok: true,
          status: 200,
          json: async () => overrides.patterns ?? MOCK_PATTERNS,
        };
      }
      // 2026-05-06 regression guard: daily/weekly summary endpoints must NOT
      // be requested by InsightsPage anymore.
      if (url.includes('summary/daily') || url.includes('summary/weekly')) {
        throw new Error(
          `InsightsPage attempted to fetch removed endpoint: ${url}. ` +
            'Daily/weekly summary cards were removed 2026-05-06.'
        );
      }
      return { ok: false, status: 404, json: async () => ({}) };
    })
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('InsightsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  async function renderPage() {
    const { default: InsightsPage } = await import('../pages/InsightsPage');
    return render(
      <MemoryRouter>
        <InsightsPage />
      </MemoryRouter>
    );
  }

  it('renders the Insights header with a Brain View button', async () => {
    setupFetchMocks();
    await renderPage();
    expect(screen.getByText(/insights/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/open brain view/i)).toBeInTheDocument();
  });

  it('renders the Recurring Patterns section', async () => {
    setupFetchMocks();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByText(/recurring patterns/i)).toBeInTheDocument();
    });
  });

  it('displays pattern themes when patterns are returned', async () => {
    setupFetchMocks();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByText(/music practice/i)).toBeInTheDocument();
      expect(screen.getByText(/morning routine/i)).toBeInTheDocument();
    });
  });

  it('shows empty-state copy when no patterns are returned', async () => {
    setupFetchMocks({ patterns: MOCK_EMPTY_PATTERNS });
    await renderPage();
    await waitFor(() => {
      expect(screen.getByText(/no patterns detected yet/i)).toBeInTheDocument();
    });
  });

  it('does NOT fetch the removed daily/weekly summary endpoints (regression guard)', async () => {
    setupFetchMocks();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByText(/recurring patterns/i)).toBeInTheDocument();
    });

    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>;
    const calls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(calls.some((u) => u.includes('summary/daily'))).toBe(false);
    expect(calls.some((u) => u.includes('summary/weekly'))).toBe(false);
  });

  it('does not crash when patterns endpoint returns an error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async () => {
        throw new Error('network down');
      })
    );
    await renderPage();
    // Page itself should still render header
    expect(screen.getByText(/insights/i)).toBeInTheDocument();
  });
});
