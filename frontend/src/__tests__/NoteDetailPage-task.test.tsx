import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const {
  mockNavigate,
  mockGetNote,
  mockUpdateNoteDetails,
  mockSearchSimilar,
  mockGetNoteLinks,
  mockDbGet,
  mockDbWhere,
  mockApiGet,
  mockApiPatch,
  mockApiPost,
} = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
  mockGetNote: vi.fn(),
  mockUpdateNoteDetails: vi.fn(),
  mockSearchSimilar: vi.fn(),
  mockGetNoteLinks: vi.fn(),
  mockDbGet: vi.fn(),
  mockDbWhere: vi.fn(),
  mockApiGet: vi.fn(),
  mockApiPatch: vi.fn(),
  mockApiPost: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../api/client', () => ({
  apiGet: mockApiGet,
  apiPatch: mockApiPatch,
  apiPost: mockApiPost,
}));

vi.mock('../api/notes', () => ({
  getNote: mockGetNote,
  updateNote: mockUpdateNoteDetails,
  deleteNote: vi.fn(),
}));

vi.mock('../api/search', () => ({
  searchSimilar: mockSearchSimilar,
}));

vi.mock('../api/links', () => ({
  getNoteLinks: mockGetNoteLinks,
  deleteLink: vi.fn(),
  createManualLink: vi.fn(),
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
vi.mock('../components/AddToCanvasModal', () => ({
  AddToCanvasModal: () => null,
}));
vi.mock('../featureFlags', () => ({
  isCanvasEnabled: () => false,
}));

import NoteDetailPage from '../pages/NoteDetailPage';

const SERVER_NOTE = {
  id: 'srv-1',
  user_id: 'u1',
  title: 'Task note',
  content: 'Main note body',
  source_type: 'text',
  category: 'Ideas',
  entities: [],
  music_metadata: {},
  processing_status: 'enriched',
  sync_status: 'synced',
  tags: [],
  due_at: null,
  done_at: null,
  priority: null,
  recurring: null,
  reminder_sent_at: null,
  created_at: '2026-05-01T00:00:00Z',
  updated_at: '2026-05-01T00:00:00Z',
};

function note(overrides: Partial<typeof SERVER_NOTE> = {}) {
  return { ...SERVER_NOTE, ...overrides };
}

function renderPage(noteId = 'srv-1') {
  return render(
    <MemoryRouter initialEntries={[`/note/${noteId}`]}>
      <Routes>
        <Route path="/note/:id" element={<NoteDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function dateDaysFromNow(days: number): Date {
  const date = new Date();
  date.setDate(date.getDate() + days);
  date.setHours(15, 30, 0, 0);
  return date;
}

function toDatetimeLocalValue(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function expectedFarDueText(date: Date): string {
  const now = new Date();
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    ...(date.getFullYear() !== now.getFullYear() ? { year: 'numeric' as const } : {}),
  }).format(date);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

beforeEach(() => {
  vi.clearAllMocks();
  mockDbGet.mockResolvedValue(undefined);
  mockDbWhere.mockReturnValue({
    equals: () => ({ first: async () => undefined }),
  });
  mockGetNote.mockResolvedValue(note());
  mockSearchSimilar.mockResolvedValue([]);
  mockGetNoteLinks.mockResolvedValue({ outgoing: [], incoming: [] });
});

describe('NoteDetailPage task panel', () => {
  it('renders a due_at deadline pill with the right text', async () => {
    const due = dateDaysFromNow(10);
    mockGetNote.mockResolvedValueOnce(note({ due_at: due.toISOString() }));

    renderPage();

    expect(
      await screen.findByText(new RegExp(escapeRegExp(expectedFarDueText(due)), 'i')),
    ).toBeInTheDocument();
    expect(screen.getByTestId('note-detail-deadline-pill')).toBeInTheDocument();
  });

  it('renders the add reminder affordance when task fields are empty', async () => {
    renderPage();

    expect(await screen.findByRole('button', { name: /\+ add reminder/i })).toBeInTheDocument();
    expect(screen.queryByTestId('note-detail-deadline-pill')).not.toBeInTheDocument();
  });

  it('edits due_at through the pill and refreshes the local view', async () => {
    const initialDue = dateDaysFromNow(10);
    const updatedDue = dateDaysFromNow(11);
    const updatedIso = new Date(toDatetimeLocalValue(updatedDue)).toISOString();
    mockGetNote.mockResolvedValueOnce(note({ due_at: initialDue.toISOString() }));
    mockApiPatch.mockResolvedValueOnce(note({ due_at: updatedIso }));

    const { container } = renderPage();
    await screen.findByText(new RegExp(escapeRegExp(expectedFarDueText(initialDue)), 'i'));

    fireEvent.click(screen.getByTestId('note-detail-deadline-pill'));
    const input = container.querySelector('input[type="datetime-local"]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: toDatetimeLocalValue(updatedDue) } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(mockApiPatch).toHaveBeenCalledWith(
        '/api/notes/srv-1',
        expect.objectContaining({ due_at: updatedIso }),
      );
    });
    expect(
      await screen.findByText(new RegExp(escapeRegExp(expectedFarDueText(updatedDue)), 'i')),
    ).toBeInTheDocument();
  });

  it('marks a note done and updates done_at locally', async () => {
    const doneAt = '2026-06-05T10:00:00.000Z';
    mockApiPost.mockResolvedValueOnce(note({ done_at: doneAt }));

    renderPage();
    const heading = await screen.findByRole('heading', { level: 1, name: /task note/i });
    fireEvent.click(screen.getByRole('button', { name: /^mark done$/i }));

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith('/api/notes/srv-1/done');
    });
    expect(await screen.findByRole('button', { name: /^mark not done$/i })).toBeInTheDocument();
    expect(heading).toHaveClass('line-through');
  });

  it('marks a done note not done and clears done_at locally', async () => {
    mockGetNote.mockResolvedValueOnce(note({ done_at: '2026-06-05T10:00:00.000Z' }));
    mockApiPost.mockResolvedValueOnce(note({ done_at: null }));

    renderPage();
    const heading = await screen.findByRole('heading', { level: 1, name: /task note/i });
    expect(heading).toHaveClass('line-through');

    fireEvent.click(screen.getByRole('button', { name: /^mark not done$/i }));

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith('/api/notes/srv-1/done');
    });
    expect(await screen.findByRole('button', { name: /^mark done$/i })).toBeInTheDocument();
    expect(heading).not.toHaveClass('line-through');
  });
});
