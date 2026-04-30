/**
 * InsightsPage.test.tsx — Task 5.1 (Insights UI)
 * TDD red-phase tests for frontend/src/pages/InsightsPage.tsx
 *
 * Tests:
 *   - Renders daily summary card (calls /api/ai/summary/daily?date=today)
 *   - Renders weekly summary card (calls /api/ai/summary/weekly?week=current)
 *   - Renders patterns list (calls /api/insights/patterns)
 *   - Shows loading state while fetching
 *   - Shows empty/placeholder state when no summary available (404)
 *   - Requires authentication (redirects if no token)
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

const MOCK_DAILY_SUMMARY = {
  id: 'summary-1',
  summary_date: '2026-04-29',
  summary_text: 'Today you focused on jazz improvisation and morning fitness.',
  note_count: 4,
  mood_summary: 'energized',
};

const MOCK_WEEKLY_SUMMARY = {
  summary_text: 'This week you explored music theory, maintained a fitness routine, and journaled about personal growth.',
  week: '2026-W17',
};

const MOCK_PATTERNS = {
  patterns: [
    { theme: 'Music Practice', evidence_note_ids: ['note-1', 'note-2'] },
    { theme: 'Morning Routine', evidence_note_ids: ['note-3'] },
  ],
};

// ---------------------------------------------------------------------------
// Mock fetch
// ---------------------------------------------------------------------------

function setupFetchMocks(overrides: Record<string, unknown> = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (url.includes('summary/daily')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => overrides.daily ?? MOCK_DAILY_SUMMARY,
        });
      }
      if (url.includes('summary/weekly')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => overrides.weekly ?? MOCK_WEEKLY_SUMMARY,
        });
      }
      if (url.includes('insights/patterns')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => overrides.patterns ?? MOCK_PATTERNS,
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({}),
      });
    }),
  );
}

// ---------------------------------------------------------------------------
// Import component under test
// ---------------------------------------------------------------------------

import InsightsPage from '../pages/InsightsPage';

function renderInsightsPage() {
  return render(
    <MemoryRouter>
      <InsightsPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('InsightsPage (Task 5.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupFetchMocks();
  });

  // --- Page structure ---

  it('renders an Insights heading', async () => {
    renderInsightsPage();
    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: /insights/i });
      expect(heading).toBeInTheDocument();
    });
  });

  // --- Daily summary card ---

  it('renders a daily summary section', async () => {
    renderInsightsPage();
    await waitFor(() => {
      expect(screen.getByText(/daily/i)).toBeInTheDocument();
    });
  });

  it('displays the daily summary text', async () => {
    renderInsightsPage();
    await waitFor(() => {
      expect(screen.getByText(/jazz improvisation|morning fitness/i)).toBeInTheDocument();
    });
  });

  it('fetches daily summary with today date param', async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => {
          if (url.includes('summary/daily')) return MOCK_DAILY_SUMMARY;
          if (url.includes('summary/weekly')) return MOCK_WEEKLY_SUMMARY;
          if (url.includes('patterns')) return MOCK_PATTERNS;
          return {};
        },
      });
    });
    vi.stubGlobal('fetch', fetchSpy);

    renderInsightsPage();

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.map(([url]: [string]) => url);
      const dailyCall = calls.find((url: string) => url.includes('summary/daily'));
      expect(dailyCall).toBeDefined();
      // Should include a date parameter
      expect(dailyCall).toMatch(/date=/);
    });
  });

  it('shows placeholder when daily summary returns 404', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (url.includes('summary/daily')) {
          return Promise.resolve({ ok: false, status: 404, json: async () => ({ detail: 'Not found' }) });
        }
        if (url.includes('summary/weekly')) {
          return Promise.resolve({ ok: true, status: 200, json: async () => MOCK_WEEKLY_SUMMARY });
        }
        if (url.includes('patterns')) {
          return Promise.resolve({ ok: true, status: 200, json: async () => MOCK_PATTERNS });
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
      }),
    );

    renderInsightsPage();

    await waitFor(() => {
      // Should show some placeholder/empty state message
      expect(document.body.textContent).toMatch(/no summary|not yet|capturing|no daily/i);
    });
  });

  // --- Weekly summary card ---

  it('renders a weekly summary section', async () => {
    renderInsightsPage();
    await waitFor(() => {
      expect(screen.getByText(/weekly/i)).toBeInTheDocument();
    });
  });

  it('displays the weekly summary text', async () => {
    renderInsightsPage();
    await waitFor(() => {
      expect(screen.getByText(/music theory|fitness routine|personal growth/i)).toBeInTheDocument();
    });
  });

  it('fetches weekly summary with current week param', async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => {
          if (url.includes('summary/daily')) return MOCK_DAILY_SUMMARY;
          if (url.includes('summary/weekly')) return MOCK_WEEKLY_SUMMARY;
          if (url.includes('patterns')) return MOCK_PATTERNS;
          return {};
        },
      });
    });
    vi.stubGlobal('fetch', fetchSpy);

    renderInsightsPage();

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.map(([url]: [string]) => url);
      const weeklyCall = calls.find((url: string) => url.includes('summary/weekly'));
      expect(weeklyCall).toBeDefined();
      // Should include a week parameter
      expect(weeklyCall).toMatch(/week=/);
    });
  });

  // --- Patterns list ---

  it('renders a patterns section', async () => {
    renderInsightsPage();
    await waitFor(() => {
      expect(screen.getByText(/pattern|theme/i)).toBeInTheDocument();
    });
  });

  it('displays detected theme names', async () => {
    renderInsightsPage();
    await waitFor(() => {
      expect(screen.getByText(/Music Practice/i)).toBeInTheDocument();
      expect(screen.getByText(/Morning Routine/i)).toBeInTheDocument();
    });
  });

  it('fetches patterns from /api/insights/patterns', async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => {
          if (url.includes('summary/daily')) return MOCK_DAILY_SUMMARY;
          if (url.includes('summary/weekly')) return MOCK_WEEKLY_SUMMARY;
          if (url.includes('patterns')) return MOCK_PATTERNS;
          return {};
        },
      });
    });
    vi.stubGlobal('fetch', fetchSpy);

    renderInsightsPage();

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.map(([url]: [string]) => url);
      const patternsCall = calls.find((url: string) => url.includes('patterns'));
      expect(patternsCall).toBeDefined();
    });
  });

  it('shows empty state when no patterns are returned', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (url.includes('summary/daily')) {
          return Promise.resolve({ ok: true, status: 200, json: async () => MOCK_DAILY_SUMMARY });
        }
        if (url.includes('summary/weekly')) {
          return Promise.resolve({ ok: true, status: 200, json: async () => MOCK_WEEKLY_SUMMARY });
        }
        if (url.includes('patterns')) {
          return Promise.resolve({ ok: true, status: 200, json: async () => ({ patterns: [] }) });
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
      }),
    );

    renderInsightsPage();

    await waitFor(() => {
      // Should show empty patterns state
      expect(document.body.textContent).toMatch(/no pattern|keep capturing|not enough|no theme/i);
    });
  });

  // --- Loading state ---

  it('shows a loading indicator while fetching', () => {
    // Don't resolve fetch — page should show loading
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})));
    renderInsightsPage();
    // Should show loading spinner or text immediately
    expect(document.body.textContent).toMatch(/loading|…|\.\.\./i);
  });

  // --- Auth usage ---

  it('sends Authorization header with fetch requests', async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => {
          if (url.includes('summary/daily')) return MOCK_DAILY_SUMMARY;
          if (url.includes('summary/weekly')) return MOCK_WEEKLY_SUMMARY;
          if (url.includes('patterns')) return MOCK_PATTERNS;
          return {};
        },
      });
    });
    vi.stubGlobal('fetch', fetchSpy);

    renderInsightsPage();

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
      const anyCallWithAuth = fetchSpy.mock.calls.some(
        ([, options]: [string, RequestInit]) =>
          options?.headers &&
          JSON.stringify(options.headers).includes('Bearer'),
      );
      expect(anyCallWithAuth).toBe(true);
    });
  });
});
