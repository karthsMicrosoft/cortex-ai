import { render, screen } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { LocalNote } from '../db';

vi.mock('../components/NoteCard', () => ({
  NoteCard: ({ note, children }: { note: LocalNote; children?: React.ReactNode }) => (
    <article data-testid={`note-card-${note.localId}`}>
      <h2 className={note.done_at ? 'line-through' : ''}>{note.content}</h2>
      {children}
    </article>
  ),
}));

const makeNote = (overrides: Partial<LocalNote> & Pick<LocalNote, 'localId' | 'content'>): LocalNote => ({
  category: 'Ideas',
  tags: [],
  syncStatus: 'synced',
  processingStatus: 'enriched',
  createdAt: new Date('2026-06-05T09:00:00Z'),
  updatedAt: new Date('2026-06-05T09:01:00Z'),
  sourceType: 'text',
  ...overrides,
});

const NOTE_FIXTURES: LocalNote[] = [
  makeNote({ localId: 'A', content: 'Plain note' }),
  makeNote({ localId: 'B', content: 'Due note', due_at: '2026-07-15T12:00:00' }),
  makeNote({
    localId: 'C',
    content: 'Completed note',
    due_at: '2026-06-06T09:00:00',
    done_at: '2026-06-05T10:00:00Z',
  }),
  makeNote({ localId: 'D', content: 'Priority note', priority: 1 }),
];

const noteDbState = { notes: NOTE_FIXTURES };

vi.mock('../db', () => ({
  db: {
    notes: {
      bulkDelete: vi.fn().mockResolvedValue(undefined),
    },
    syncQueue: {
      toArray: vi.fn().mockResolvedValue([]),
      bulkDelete: vi.fn().mockResolvedValue(undefined),
    },
  },
}));

vi.mock('../hooks/useNotes', () => ({
  useNotes: () => noteDbState.notes,
}));

vi.mock('../components/SyncIndicator', () => ({
  SyncIndicator: () => <div data-testid="sync-indicator" />,
}));

const { mockAuthState, mockUseAuthStore } = vi.hoisted(() => {
  const mockAuthState = { accessToken: 'test-token', user: null };
  const mockUseAuthStore = Object.assign(
    (selector: (s: typeof mockAuthState) => unknown) => selector(mockAuthState),
    { getState: () => mockAuthState, subscribe: () => () => {}, setState: () => {} },
  );
  return { mockAuthState, mockUseAuthStore };
});
vi.mock('../store/authStore', () => ({ useAuthStore: mockUseAuthStore }));

vi.stubGlobal(
  'fetch',
  vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ items: [], total: 0 }),
  }),
);

import LibraryPage from '../pages/LibraryPage';

function renderLibraryPage() {
  return render(
    <MemoryRouter>
      <LibraryPage />
    </MemoryRouter>,
  );
}

describe('LibraryPage deadline pill', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-05T10:00:00Z'));
    noteDbState.notes = NOTE_FIXTURES;
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('does not render a pill for notes without task fields', () => {
    renderLibraryPage();
    expect(screen.queryByTestId('library-deadline-pill-A')).toBeNull();
  });

  it('renders a due date pill with date text', () => {
    renderLibraryPage();
    expect(screen.getByTestId('library-deadline-pill-B')).toHaveTextContent(/Jul\s+15/i);
  });

  it('renders and dims completed note cards', () => {
    renderLibraryPage();
    expect(screen.getByTestId('library-deadline-pill-C')).toBeInTheDocument();
    expect(screen.getByTestId('library-note-card-C')).toHaveClass('opacity-60');
  });

  it('renders priority-only pills', () => {
    renderLibraryPage();
    expect(screen.getByTestId('library-deadline-pill-D')).toHaveTextContent('High');
  });
});
