/**
 * NoteDetailPage-canvas.test.tsx — PR C: "Add to Canvas" button on note detail.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const {
  mockNavigate,
  mockGetNote,
  mockGetNoteLinks,
  mockSearchSimilar,
  mockDbGet,
  mockDbWhere,
} = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
  mockGetNote: vi.fn(),
  mockGetNoteLinks: vi.fn(),
  mockSearchSimilar: vi.fn(),
  mockDbGet: vi.fn(),
  mockDbWhere: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  );
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../api/notes', () => ({
  getNote: mockGetNote,
  updateNote: vi.fn(),
  deleteNote: vi.fn(),
}));
vi.mock('../api/search', () => ({ searchSimilar: mockSearchSimilar }));
vi.mock('../api/links', () => ({
  getNoteLinks: mockGetNoteLinks,
  deleteLink: vi.fn(),
  createManualLink: vi.fn(),
}));
vi.mock('../api/canvas', () => ({
  listCanvases: vi.fn(() => Promise.resolve({ items: [], total: 0 })),
  createCanvas: vi.fn(),
  addCanvasItem: vi.fn(),
}));

vi.mock('../components/LinkPicker', () => ({
  LinkPicker: () => <div data-testid="link-picker-stub" />,
}));
vi.mock('../components/NoteEditor', () => ({
  NoteEditor: () => <div data-testid="note-editor-stub" />,
}));
vi.mock('../components/MusicPlayer', () => ({ MusicPlayer: () => null }));
vi.mock('../components/ProcessingBadge', () => ({ ProcessingBadge: () => null }));
vi.mock('../components/ShadowReaderPrompt', () => ({ ShadowReaderPrompt: () => null }));

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

import NoteDetailPage from '../pages/NoteDetailPage';

const SERVER_NOTE = {
  id: 'srv-1',
  user_id: 'u1',
  title: 'My note',
  content: 'Hello',
  source_type: 'text',
  category: 'Ideas',
  entities: [],
  music_metadata: {},
  processing_status: 'enriched',
  sync_status: 'synced',
  tags: [],
  aliases: [],
  created_at: '2026-05-01T00:00:00Z',
  updated_at: '2026-05-01T00:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockDbGet.mockResolvedValue(undefined);
  mockDbWhere.mockReturnValue({
    equals: () => ({ first: async () => undefined }),
  });
  mockGetNote.mockResolvedValue(SERVER_NOTE);
  mockGetNoteLinks.mockResolvedValue({ outgoing: [], incoming: [] });
  mockSearchSimilar.mockResolvedValue([]);
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/note/srv-1']}>
      <Routes>
        <Route path="/note/:id" element={<NoteDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('NoteDetailPage — Add to Canvas (PR C)', () => {
  it('renders the "Add to Canvas" button once the note loads', async () => {
    renderPage();
    expect(await screen.findByTestId('note-detail-add-to-canvas')).toBeInTheDocument();
  });

  it('opens the AddToCanvasModal when clicked', async () => {
    renderPage();
    const btn = await screen.findByTestId('note-detail-add-to-canvas');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByTestId('add-to-canvas-modal')).toBeInTheDocument();
    });
  });
});
