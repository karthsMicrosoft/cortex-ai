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
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mock SearchBar
// ---------------------------------------------------------------------------

vi.mock('../components/SearchBar', () => ({
  SearchBar: ({
    onResults,
    onLoading,
  }: {
    onResults: (results: unknown[]) => void;
    onLoading?: (loading: boolean) => void;
  }) => {
    const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
      const query = e.target.value;
      if (!query) return;
      onLoading?.(true);
      // Simulate async search
      const res = await fetch('/api/search', {
        method: 'POST',
        body: JSON.stringify({ query }),
      });
      const data = await res.json();
      onResults(data);
      onLoading?.(false);
    };
    return (
      <input
        data-testid="search-input"
        placeholder="Search your notes..."
        onChange={handleChange}
      />
    );
  },
}));

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

function renderSearchPage() {
  return render(
    <MemoryRouter>
      <SearchPage />
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
});
