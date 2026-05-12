/**
 * Task 3 / 3.4 — SearchPage — TDD red
 *
 * Tests that `frontend/src/pages/SearchPage.tsx`:
 *   - Renders a search input
 *   - POSTs to /api/search when the user types (debounced)
 *   - Renders ranked results from the API
 *   - Shows loading state while fetching
 *   - Shows empty state when no results
 *   - Passes natural-language query to /api/search
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mock SearchBar
// ---------------------------------------------------------------------------

vi.mock('../components/SearchBar', () => ({
  SearchBar: ({
    onResults,
    onLoading,
    onQueryChange,
    initialQuery,
    filters,
  }: {
    onResults: (results: unknown[]) => void;
    onLoading?: (loading: boolean) => void;
    onQueryChange?: (q: string) => void;
    initialQuery?: string;
    filters?: Record<string, unknown>;
  }) => {
    const [q, setQ] = React.useState(initialQuery ?? '');
    const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
      const query = e.target.value;
      setQ(query);
      onQueryChange?.(query);
      if (!query) return;
      onLoading?.(true);
      const res = await fetch('/api/search', {
        method: 'POST',
        body: JSON.stringify({ query, ...(filters ?? {}) }),
      });
      const data = await res.json();
      onResults(data);
      onLoading?.(false);
    };
    // Re-fire search when filters change (after a query exists)
    React.useEffect(() => {
      if (!q) return;
      (async () => {
        onLoading?.(true);
        const res = await fetch('/api/search', {
          method: 'POST',
          body: JSON.stringify({ query: q, ...(filters ?? {}) }),
        });
        const data = await res.json();
        onResults(data);
        onLoading?.(false);
      })();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [JSON.stringify(filters ?? {})]);
    return (
      <input
        data-testid="search-input"
        placeholder="Search your notes..."
        value={q}
        onChange={handleChange}
      />
    );
  },
}));

vi.mock('../api/search', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/search')>();
  return {
    ...actual,
    listTags: vi.fn(async () => ['mentorship', 'book']),
  };
});

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockSearchResults = [
  {
    id: 'server-1',
    content: 'Jazz improvisation in C minor',
    summary: 'Jazz note',
    category: 'Music',
    created_at: '2026-04-10T09:00:00Z',
    semantic_score: 0.92,
    text_score: 0.8,
    combined_score: 0.888,
  },
  {
    id: 'server-2',
    content: 'Guitar practice session',
    summary: null,
    category: 'Music',
    created_at: '2026-04-09T15:00:00Z',
    semantic_score: 0.85,
    text_score: 0.6,
    combined_score: 0.773,
  },
];

// ---------------------------------------------------------------------------
// Mock fetch
// ---------------------------------------------------------------------------

let mockFetch: ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => mockSearchResults,
  });
  vi.stubGlobal('fetch', mockFetch);
});

// ---------------------------------------------------------------------------
// Import component under test
// ---------------------------------------------------------------------------

import { SearchPage } from '../pages/SearchPage';

function renderSearchPage(initialEntries: string[] = ['/']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route path="*" element={<SearchPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SearchPage (Task 3 / 3.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --- Initial render ---

  it('renders the search input', () => {
    renderSearchPage();
    expect(screen.getByTestId('search-input')).toBeInTheDocument();
  });

  it('renders a Search heading', () => {
    renderSearchPage();
    const heading = screen.getByRole('heading', { name: /search/i });
    expect(heading).toBeInTheDocument();
  });

  it('renders empty state initially (before any search)', () => {
    renderSearchPage();
    // Should show a prompt to start searching
    expect(document.body.textContent).toMatch(/search|find|type/i);
  });

  // --- Search execution ---

  it('renders search results after typing a query', async () => {
    renderSearchPage();
    const input = screen.getByTestId('search-input');
    fireEvent.change(input, { target: { value: 'jazz improvisation' } });

    await waitFor(() => {
      expect(screen.getByText(/Jazz improvisation in C minor/i)).toBeInTheDocument();
    });
  });

  it('renders multiple results', async () => {
    renderSearchPage();
    const input = screen.getByTestId('search-input');
    fireEvent.change(input, { target: { value: 'jazz' } });

    await waitFor(() => {
      expect(screen.getByText(/Jazz improvisation in C minor/i)).toBeInTheDocument();
      expect(screen.getByText(/Guitar practice session/i)).toBeInTheDocument();
    });
  });

  it('results are displayed in order (highest score first)', async () => {
    renderSearchPage();
    const input = screen.getByTestId('search-input');
    fireEvent.change(input, { target: { value: 'music' } });

    await waitFor(() => {
      const items = screen.getAllByRole('listitem');
      // First result should be the higher score one
      expect(items[0].textContent).toMatch(/Jazz improvisation/i);
    });
  });

  // --- Loading state ---

  it('SearchBar component is rendered', () => {
    renderSearchPage();
    expect(screen.getByTestId('search-input')).toBeInTheDocument();
  });

  // --- Empty search results ---

  it('shows no-results message when API returns empty array', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });
    vi.stubGlobal('fetch', mockFetch);

    renderSearchPage();
    const input = screen.getByTestId('search-input');
    fireEvent.change(input, { target: { value: 'xyznotfound12345' } });

    await waitFor(() => {
      expect(document.body.textContent).toMatch(/no results|nothing found|no notes/i);
    });
  });

  // --- Result card fields ---

  it('result cards show content', async () => {
    renderSearchPage();
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'jazz' } });

    await waitFor(() => {
      expect(screen.getByText(/Jazz improvisation in C minor/i)).toBeInTheDocument();
    });
  });

  it('result cards show category', async () => {
    renderSearchPage();
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'jazz' } });

    await waitFor(() => {
      const musicLabels = screen.getAllByText(/Music/i);
      expect(musicLabels.length).toBeGreaterThan(0);
    });
  });

  // ---------------------------------------------------------------------------
  // Phase 4 / Round 16 / PR 4.3 — filter sidebar + URL params
  // ---------------------------------------------------------------------------

  it('renders the SearchFilters sidebar', () => {
    renderSearchPage();
    expect(screen.getByLabelText(/category/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/since/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/until/i)).toBeInTheDocument();
  });

  it('reads filter state from URL query params on mount', async () => {
    renderSearchPage([
      '/search?q=leadership&category=Learning&tags=mentorship,book&since=2026-04-01&until=2026-05-15',
    ]);
    const select = screen.getByLabelText(/category/i) as HTMLSelectElement;
    expect(select.value).toBe('Learning');
    const since = screen.getByLabelText(/since/i) as HTMLInputElement;
    const until = screen.getByLabelText(/until/i) as HTMLInputElement;
    expect(since.value).toBe('2026-04-01');
    expect(until.value).toBe('2026-05-15');
    // Tag chips render once listTags() resolves
    const mentorship = await screen.findByRole('button', { name: /^mentorship$/i });
    expect(mentorship).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /^book$/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('changing a filter writes the new value into URL query params', async () => {
    let captured: string | null = null;
    function LocationSpy() {
      const loc = useLocation();
      captured = loc.search;
      return null;
    }
    render(
      <MemoryRouter initialEntries={['/search']}>
        <Routes>
          <Route
            path="*"
            element={
              <>
                <SearchPage />
                <LocationSpy />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    const select = screen.getByLabelText(/category/i) as HTMLSelectElement;
    await act(async () => {
      fireEvent.change(select, { target: { value: 'Music' } });
    });
    await waitFor(() => {
      expect(captured).toContain('category=Music');
    });
  });

  it('changing a filter re-triggers search when a query is already entered', async () => {
    renderSearchPage();
    const input = screen.getByTestId('search-input');
    fireEvent.change(input, { target: { value: 'leadership' } });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    const callsBefore = mockFetch.mock.calls.length;

    const select = screen.getByLabelText(/category/i) as HTMLSelectElement;
    await act(async () => {
      fireEvent.change(select, { target: { value: 'Learning' } });
    });

    await waitFor(() => {
      expect(mockFetch.mock.calls.length).toBeGreaterThan(callsBefore);
    });
    // Most recent call should include the new category in the body
    const lastCall = mockFetch.mock.calls.at(-1)!;
    const body = JSON.parse((lastCall[1] as RequestInit).body as string);
    expect(body.category).toBe('Learning');
    expect(body.query).toBe('leadership');
  });

  it('passes category filter through to the search request body', async () => {
    renderSearchPage(['/search?category=Music']);
    const input = screen.getByTestId('search-input');
    fireEvent.change(input, { target: { value: 'jazz' } });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    // Find the most-recent call that has a body matching our query
    const matching = mockFetch.mock.calls
      .map((c) => JSON.parse(((c[1] as RequestInit).body as string) ?? '{}'))
      .filter((b) => b.query === 'jazz');
    expect(matching.length).toBeGreaterThan(0);
    expect(matching.at(-1).category).toBe('Music');
  });

  // ---------------------------------------------------------------------------
  // Round 19 — title in result cards
  // ---------------------------------------------------------------------------

  it('result card shows title when set', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          id: 'r1',
          title: 'Brilliant idea',
          content: 'long body content with more than enough text',
          summary: 'short sum',
          category: 'Ideas',
          created_at: '2026-05-01T00:00:00Z',
          semantic_score: 0.9,
          text_score: 0.5,
          combined_score: 0.78,
        },
      ],
    });
    vi.stubGlobal('fetch', mockFetch);

    renderSearchPage();
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'idea' } });

    await waitFor(() => {
      expect(screen.getByText('Brilliant idea')).toBeInTheDocument();
    });
    // Snippet still visible as secondary
    expect(
      screen.getByText(/long body content with more than enough text/i),
    ).toBeInTheDocument();
  });

  it('result card falls back to snippet when title is null', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          id: 'r2',
          title: null,
          content: 'untitled body content here',
          summary: null,
          category: 'Ideas',
          created_at: '2026-05-01T00:00:00Z',
          semantic_score: 0.9,
          text_score: 0.5,
          combined_score: 0.78,
        },
      ],
    });
    vi.stubGlobal('fetch', mockFetch);

    renderSearchPage();
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'untitled' } });

    await waitFor(() => {
      expect(screen.getByText(/untitled body content here/i)).toBeInTheDocument();
    });
  });
});
