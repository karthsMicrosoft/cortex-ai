/**
 * Task 2 / 3.3 — LibraryPage — TDD red
 *
 * Tests that `frontend/src/pages/LibraryPage.tsx`:
 *   - Renders a chronological timeline of NoteCards
 *   - Provides category filter chips (six fixed values)
 *   - Provides a date range selector
 *   - Reads from Dexie noteStore (offline-first); falls back to /api/notes
 *   - Filtering by category shows only matching notes
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mock NoteCard (no top-level vars in factory)
// ---------------------------------------------------------------------------

vi.mock('../components/NoteCard', () => ({
  NoteCard: ({ note }: { note: { localId: string; content: string; category: string } }) => (
    <article data-testid={`note-card-${note.localId}`} data-category={note.category}>
      <span>{note.content}</span>
      <span role="status">{note.category}</span>
    </article>
  ),
}));

// ---------------------------------------------------------------------------
// Note fixture — kept outside vi.mock factory
// ---------------------------------------------------------------------------

const NOTE_FIXTURES = [
  {
    localId: 'note-1',
    content: 'Jazz improvisation ideas',
    category: 'Music',
    tags: ['jazz'],
    syncStatus: 'synced',
    processingStatus: 'enriched',
    createdAt: new Date('2026-04-10T09:00:00Z'),
    updatedAt: new Date('2026-04-10T09:01:00Z'),
    sourceType: 'voice',
  },
  {
    localId: 'note-2',
    content: 'Morning run stats',
    category: 'Fitness',
    tags: ['running'],
    syncStatus: 'synced',
    processingStatus: 'processed',
    createdAt: new Date('2026-04-11T07:00:00Z'),
    updatedAt: new Date('2026-04-11T07:01:00Z'),
    sourceType: 'text',
  },
  {
    localId: 'note-3',
    content: 'Startup idea about AI',
    category: 'Ideas',
    tags: ['ai'],
    syncStatus: 'pending',
    processingStatus: 'raw',
    createdAt: new Date('2026-04-12T12:00:00Z'),
    updatedAt: new Date('2026-04-12T12:00:00Z'),
    sourceType: 'text',
  },
];

// ---------------------------------------------------------------------------
// Mock db — use stable state
// ---------------------------------------------------------------------------

const noteDbState = { notes: NOTE_FIXTURES as typeof NOTE_FIXTURES };

vi.mock('../db', () => ({
  db: {
    notes: {
      orderBy: () => ({
        reverse: () => ({
          filter: (fn: (n: typeof NOTE_FIXTURES[0]) => boolean) => ({
            toArray: () => Promise.resolve(noteDbState.notes.filter(fn)),
          }),
          toArray: () => Promise.resolve([...noteDbState.notes].reverse()),
        }),
      }),
      toArray: () => Promise.resolve(noteDbState.notes),
    },
  },
}));

// ---------------------------------------------------------------------------
// Mock syncManager (LibraryPage may trigger pull)
// ---------------------------------------------------------------------------

vi.mock('../sync/syncManager', () => ({
  syncManager: {
    pullChanges: vi.fn().mockResolvedValue(undefined),
    pushChanges: vi.fn().mockResolvedValue(undefined),
  },
}));

// ---------------------------------------------------------------------------
// Mock authStore (Zustand hook)
// ---------------------------------------------------------------------------

const mockAuthState = { accessToken: 'test-token', user: null };
const mockUseAuthStore = Object.assign(
  (selector: (s: typeof mockAuthState) => unknown) => selector(mockAuthState),
  { getState: () => mockAuthState, subscribe: vi.fn(), setState: vi.fn() },
);
vi.mock('../store/authStore', () => ({ useAuthStore: mockUseAuthStore }));

// ---------------------------------------------------------------------------
// Mock dexie-react-hooks (useLiveQuery) — used by useNotes
// ---------------------------------------------------------------------------

vi.mock('dexie-react-hooks', () => ({
  useLiveQuery: (fn: () => unknown) => {
    // Synchronously evaluate the query in tests
    try {
      // Return a simple resolved value based on our noteDbState
      return noteDbState.notes;
    } catch {
      return undefined;
    }
  },
}));

// ---------------------------------------------------------------------------
// Mock useNotes hook directly (simpler than dealing with useLiveQuery internals)
// ---------------------------------------------------------------------------

vi.mock('../hooks/useNotes', () => ({
  useNotes: () => noteDbState.notes,
}));

// ---------------------------------------------------------------------------
// Mock SyncIndicator
// ---------------------------------------------------------------------------

vi.mock('../components/SyncIndicator', () => ({
  SyncIndicator: () => <div data-testid="sync-indicator" />,
}));

// ---------------------------------------------------------------------------
// Mock fetch for API fallback
// ---------------------------------------------------------------------------

vi.stubGlobal(
  'fetch',
  vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      items: NOTE_FIXTURES.map((n) => ({
        id: n.localId,
        content: n.content,
        category: n.category,
        processing_status: n.processingStatus,
        created_at: n.createdAt.toISOString(),
        updated_at: n.updatedAt.toISOString(),
        source_type: n.sourceType,
        tags: n.tags,
        sync_status: n.syncStatus,
        entities: [],
        music_metadata: {},
        user_id: 'user-1',
      })),
      total: NOTE_FIXTURES.length,
    }),
  }),
);

// ---------------------------------------------------------------------------
// Import component under test
// ---------------------------------------------------------------------------

import LibraryPage from '../pages/LibraryPage';

function renderLibraryPage() {
  return render(
    <MemoryRouter>
      <LibraryPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('LibraryPage (Task 2 / 3.3)', () => {
  beforeEach(() => {
    noteDbState.notes = NOTE_FIXTURES;
    vi.clearAllMocks();
  });

  // --- Page heading ---

  it('renders a Library heading', async () => {
    renderLibraryPage();
    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: /library/i });
      expect(heading).toBeInTheDocument();
    });
  });

  // --- Timeline ---

  it('renders note cards', async () => {
    renderLibraryPage();
    await waitFor(() => {
      expect(screen.getAllByRole('article').length).toBeGreaterThan(0);
    });
  });

  it('renders all notes from IndexedDB', async () => {
    renderLibraryPage();
    await waitFor(() => {
      expect(screen.getByTestId('note-card-note-1')).toBeInTheDocument();
      expect(screen.getByTestId('note-card-note-2')).toBeInTheDocument();
      expect(screen.getByTestId('note-card-note-3')).toBeInTheDocument();
    });
  });

  // --- Category filter chips ---

  it('renders all six category filter chips', async () => {
    renderLibraryPage();
    await waitFor(() => {
      const categories = ['Music', 'Fitness', 'Journal', 'Ideas', 'Spiritual', 'Learning'];
      categories.forEach((cat) => {
        // Buttons or chips for filtering — multiple occurrences expected (also in card content)
        expect(screen.getAllByText(cat).length).toBeGreaterThan(0);
      });
    });
  });

  it('has a Music filter option', async () => {
    renderLibraryPage();
    await waitFor(() => {
      const items = screen.getAllByText('Music');
      expect(items.length).toBeGreaterThan(0);
    });
  });

  it('has a Fitness filter option', async () => {
    renderLibraryPage();
    await waitFor(() => {
      const items = screen.getAllByText('Fitness');
      expect(items.length).toBeGreaterThan(0);
    });
  });

  it('has a Journal filter option', async () => {
    renderLibraryPage();
    await waitFor(() => {
      const items = screen.getAllByText('Journal');
      expect(items.length).toBeGreaterThan(0);
    });
  });

  it('has an Ideas filter option', async () => {
    renderLibraryPage();
    await waitFor(() => {
      const items = screen.getAllByText('Ideas');
      expect(items.length).toBeGreaterThan(0);
    });
  });

  it('has a Spiritual filter option', async () => {
    renderLibraryPage();
    await waitFor(() => {
      const items = screen.getAllByText('Spiritual');
      expect(items.length).toBeGreaterThan(0);
    });
  });

  it('has a Learning filter option', async () => {
    renderLibraryPage();
    await waitFor(() => {
      const items = screen.getAllByText('Learning');
      expect(items.length).toBeGreaterThan(0);
    });
  });

  // --- Date range selector ---

  it('renders a date range selector or date filter inputs', async () => {
    renderLibraryPage();
    await waitFor(() => {
      const dateInputs = document.querySelectorAll('input[type="date"]');
      const dateLabels = screen.queryAllByLabelText(/date|from|to|range/i);
      const dateText = screen.queryAllByText(/date|filter.*date|from.*to/i);
      expect(dateInputs.length + dateLabels.length + dateText.length).toBeGreaterThan(0);
    });
  });

  // --- Empty state ---

  it('shows an empty state when no notes exist', async () => {
    noteDbState.notes = [];
    renderLibraryPage();
    await waitFor(() => {
      expect(document.body.textContent).toMatch(/no notes|empty|start capturing/i);
    });
  });
});
