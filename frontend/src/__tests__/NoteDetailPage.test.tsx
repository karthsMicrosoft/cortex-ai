/**
 * NoteDetailPage.test.tsx — PR 6.1 Backlinks panel tests.
 *
 * Scope (only the Backlinks panel — existing detail rendering is exercised
 * elsewhere; here we mock the rest so we can focus on the new section):
 *   - panel collapsed by default, expand triggers fetch
 *   - incoming + outgoing rendering
 *   - empty state
 *   - link click → navigate
 *   - error state + retry
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Hoisted mocks
// ---------------------------------------------------------------------------
const {
  mockNavigate,
  mockGetNote,
  mockSearchSimilar,
  mockGetNoteLinks,
  mockDbGet,
  mockDbWhere,
} = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
  mockGetNote: vi.fn(),
  mockSearchSimilar: vi.fn(),
  mockGetNoteLinks: vi.fn(),
  mockDbGet: vi.fn(),
  mockDbWhere: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  );
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../api/notes', () => ({
  getNote: mockGetNote,
  updateNote: vi.fn(),
  deleteNote: vi.fn(),
}));

vi.mock('../api/search', () => ({
  searchSimilar: mockSearchSimilar,
}));

vi.mock('../api/links', () => ({
  getNoteLinks: mockGetNoteLinks,
}));

vi.mock('../db', () => ({
  db: {
    notes: {
      get: mockDbGet,
      where: mockDbWhere,
      update: vi.fn(),
      delete: vi.fn(),
    },
  },
}));

// Stub side components so they don't error
vi.mock('../components/NoteEditor', () => ({
  NoteEditor: () => <div data-testid="note-editor-stub" />,
}));
vi.mock('../components/MusicPlayer', () => ({
  MusicPlayer: () => null,
}));
vi.mock('../components/ProcessingBadge', () => ({
  ProcessingBadge: () => null,
}));
vi.mock('../components/ShadowReaderPrompt', () => ({
  ShadowReaderPrompt: () => null,
}));

import NoteDetailPage from '../pages/NoteDetailPage';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SERVER_NOTE = {
  id: 'srv-1',
  user_id: 'u1',
  content: 'Main note body',
  source_type: 'text',
  category: 'Ideas',
  entities: [],
  music_metadata: {},
  processing_status: 'enriched',
  sync_status: 'synced',
  tags: [],
  created_at: '2026-05-01T00:00:00Z',
  updated_at: '2026-05-01T00:00:00Z',
};

function renderPage(noteId = 'srv-1') {
  return render(
    <MemoryRouter initialEntries={[`/note/${noteId}`]}>
      <Routes>
        <Route path="/note/:id" element={<NoteDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockDbGet.mockResolvedValue(undefined);
  mockDbWhere.mockReturnValue({
    equals: () => ({ first: async () => undefined }),
  });
  mockGetNote.mockResolvedValue(SERVER_NOTE);
  mockSearchSimilar.mockResolvedValue([]);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('NoteDetailPage — Backlinks panel (PR 6.1)', () => {
  it('renders Backlinks panel collapsed by default and does not fetch', async () => {
    renderPage();
    // Wait for initial load
    await screen.findByTestId('note-editor-stub');
    expect(screen.getByRole('button', { name: /backlinks/i })).toBeInTheDocument();
    // Body is not visible while collapsed — no fetch triggered
    expect(mockGetNoteLinks).not.toHaveBeenCalled();
  });

  it('clicking expands the panel and fetches links', async () => {
    mockGetNoteLinks.mockResolvedValueOnce({ outgoing: [], incoming: [] });
    renderPage();
    await screen.findByTestId('note-editor-stub');

    fireEvent.click(screen.getByRole('button', { name: /backlinks/i }));

    await waitFor(() => {
      expect(mockGetNoteLinks).toHaveBeenCalledWith('srv-1');
    });
  });

  it('renders incoming links with a "via" badge', async () => {
    mockGetNoteLinks.mockResolvedValueOnce({
      outgoing: [],
      incoming: [
        {
          note_id: 'in-1',
          title: 'Inbound note',
          summary: null,
          category: 'Learning',
          link_type: 'wiki',
          score: null,
        },
      ],
    });
    renderPage();
    await screen.findByTestId('note-editor-stub');
    fireEvent.click(screen.getByRole('button', { name: /backlinks/i }));

    expect(await screen.findByText(/inbound note/i)).toBeInTheDocument();
    expect(screen.getByText(/via wiki/i)).toBeInTheDocument();
  });

  it('renders outgoing links with score for semantic', async () => {
    mockGetNoteLinks.mockResolvedValueOnce({
      outgoing: [
        {
          note_id: 'out-1',
          title: 'Outbound note',
          summary: 'sumr',
          category: 'Ideas',
          link_type: 'semantic',
          score: 0.87,
        },
      ],
      incoming: [],
    });
    renderPage();
    await screen.findByTestId('note-editor-stub');
    fireEvent.click(screen.getByRole('button', { name: /backlinks/i }));

    expect(await screen.findByText(/outbound note/i)).toBeInTheDocument();
    expect(screen.getByText(/87%/)).toBeInTheDocument();
    expect(screen.getByText(/via semantic/i)).toBeInTheDocument();
  });

  it('shows empty-state message when no incoming links', async () => {
    mockGetNoteLinks.mockResolvedValueOnce({ outgoing: [], incoming: [] });
    renderPage();
    await screen.findByTestId('note-editor-stub');
    fireEvent.click(screen.getByRole('button', { name: /backlinks/i }));

    expect(
      await screen.findByText(/no notes link to this one yet/i),
    ).toBeInTheDocument();
  });

  it('clicking a backlink navigates to /note/:id', async () => {
    mockGetNoteLinks.mockResolvedValueOnce({
      outgoing: [],
      incoming: [
        {
          note_id: 'in-42',
          title: 'Click me',
          summary: null,
          category: 'Ideas',
          link_type: 'manual',
          score: null,
        },
      ],
    });
    renderPage();
    await screen.findByTestId('note-editor-stub');
    fireEvent.click(screen.getByRole('button', { name: /backlinks/i }));

    const link = await screen.findByRole('button', { name: /click me/i });
    fireEvent.click(link);
    expect(mockNavigate).toHaveBeenCalledWith('/note/in-42');
  });
});
