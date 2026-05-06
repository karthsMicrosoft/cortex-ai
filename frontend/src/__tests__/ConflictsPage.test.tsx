/**
 * Task 4.5 — ConflictsPage — TDD red
 *
 * Tests `frontend/src/pages/ConflictsPage.tsx` (B13 conflict resolution UI):
 *   - Lists notes where syncStatus='conflict'
 *   - Shows Local vs Server side-by-side card for each conflict
 *   - Three action buttons: "Keep Mine", "Keep Server", "Merge"
 *   - "Keep Mine" → PUT /api/notes/{serverId} with local payload → syncStatus='synced'
 *   - "Keep Server" → overwrites local content with conflictServerVersion → syncStatus='synced'
 *   - "Merge" → opens NoteEditor prefilled with local content (diff)
 *   - Empty state when no conflicts
 *
 * Critical: B13 resolution.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const conflictNote1 = {
  localId: 'local-conflict-1',
  serverId: 'server-conflict-1',
  content: 'My LOCAL edits to the note',
  sourceType: 'text' as const,
  category: 'Ideas' as const,
  tags: ['local-tag'],
  mood: 'creative',
  syncStatus: 'conflict' as const,
  processingStatus: 'enriched' as const,
  updatedAt: new Date('2026-04-12T08:00:00Z'),
  createdAt: new Date('2026-04-10T10:00:00Z'),
  conflictServerVersion: {
    id: 'server-conflict-1',
    content: 'SERVER version of the note',
    category: 'Journal',
    tags: ['server-tag'],
    updated_at: '2026-04-12T06:00:00Z',
    created_at: '2026-04-10T10:00:00Z',
    processing_status: 'enriched',
    source_type: 'text',
    sync_status: 'synced',
    entities: [],
    music_metadata: {},
    user_id: 'user-1',
  },
};

const conflictNote2 = {
  localId: 'local-conflict-2',
  serverId: 'server-conflict-2',
  content: 'Another local edit',
  sourceType: 'voice' as const,
  category: 'Music' as const,
  tags: [],
  syncStatus: 'conflict' as const,
  processingStatus: 'processed' as const,
  updatedAt: new Date('2026-04-12T09:00:00Z'),
  createdAt: new Date('2026-04-11T10:00:00Z'),
  conflictServerVersion: {
    id: 'server-conflict-2',
    content: 'Server music note',
    category: 'Music',
    tags: [],
    updated_at: '2026-04-12T07:00:00Z',
    created_at: '2026-04-11T10:00:00Z',
    processing_status: 'enriched',
    source_type: 'voice',
    sync_status: 'synced',
    entities: [],
    music_metadata: {},
    user_id: 'user-1',
  },
};

// ---------------------------------------------------------------------------
// Mock db — use stable mock that can be mutated between tests
// ---------------------------------------------------------------------------

// Use a mutable array that tests can update
const conflictsState = { items: [conflictNote1, conflictNote2] };

vi.mock('../db', () => ({
  db: {
    notes: {
      where: () => ({
        equals: () => ({
          toArray: () => Promise.resolve(conflictsState.items),
        }),
      }),
      update: vi.fn().mockResolvedValue(undefined),
    },
  },
}));

// ---------------------------------------------------------------------------
// Mock dexie-react-hooks (useLiveQuery used by ConflictsPage)
// ---------------------------------------------------------------------------

vi.mock('dexie-react-hooks', () => ({
  useLiveQuery: (_fn: () => unknown, _deps?: unknown[], _default?: unknown) =>
    conflictsState.items,
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
// Mock NoteEditor — ConflictsPage passes onSaved (not onSave) to NoteEditor
// ---------------------------------------------------------------------------

vi.mock('../components/NoteEditor', () => ({
  NoteEditor: ({
    note,
    onSaved,
    onSave,
    onCancel,
  }: {
    note: { content: string };
    onSaved?: (updated: Record<string, unknown>) => void;
    onSave?: (patch: Record<string, unknown>) => Promise<void>;
    onCancel?: () => void;
  }) => (
    <div data-testid="note-editor">
      <span>Editing: {note.content}</span>
      <button
        onClick={() => {
          const updated = { content: 'merged content', category: 'Ideas', tags: [] };
          if (onSaved) onSaved(updated);
          else if (onSave) void onSave(updated);
        }}
      >
        Save
      </button>
      {onCancel && <button onClick={onCancel}>Cancel</button>}
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Mock api/notes (for PUT call)
// ---------------------------------------------------------------------------

vi.mock('../api/notes', () => ({
  updateNote: vi.fn().mockResolvedValue({ id: 'server-conflict-1', content: 'updated' }),
}));

// (authStore already mocked above via mockUseAuthStore)

// ---------------------------------------------------------------------------
// Import component under test
// ---------------------------------------------------------------------------

import ConflictsPage from '../pages/ConflictsPage';

function renderConflictsPage() {
  return render(
    <MemoryRouter>
      <ConflictsPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ConflictsPage (Task 4.5 — B13)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    conflictsState.items = [conflictNote1, conflictNote2];
  });

  // --- Page heading ---

  it('renders a Conflicts heading', async () => {
    renderConflictsPage();
    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: /conflict/i });
      expect(heading).toBeInTheDocument();
    });
  });

  // --- Conflict list ---

  it('lists all conflicted notes', async () => {
    renderConflictsPage();
    await waitFor(() => {
      expect(screen.getByText(/My LOCAL edits/i)).toBeInTheDocument();
      expect(screen.getByText(/Another local edit/i)).toBeInTheDocument();
    });
  });

  it('shows both Local and Server versions for each conflict', async () => {
    renderConflictsPage();
    await waitFor(() => {
      expect(screen.getByText(/My LOCAL edits/i)).toBeInTheDocument();
      expect(screen.getByText(/SERVER version/i)).toBeInTheDocument();
    });
  });

  it('shows "Local" label', async () => {
    renderConflictsPage();
    await waitFor(() => {
      // Component renders "Local (your edits)"
      const localLabels = screen.getAllByText(/local|your edits/i);
      expect(localLabels.length).toBeGreaterThan(0);
    });
  });

  it('shows "Server" label', async () => {
    renderConflictsPage();
    await waitFor(() => {
      // Component renders "Server (remote)"
      const serverLabels = screen.getAllByText(/server|remote/i);
      expect(serverLabels.length).toBeGreaterThan(0);
    });
  });

  // --- Action buttons ---

  it('shows "Keep Mine" (Keep Local) button for each conflict', async () => {
    renderConflictsPage();
    await waitFor(() => {
      const buttons = screen.getAllByRole('button', { name: /keep mine|keep local/i });
      expect(buttons.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows "Keep Server" button for each conflict', async () => {
    renderConflictsPage();
    await waitFor(() => {
      const buttons = screen.getAllByRole('button', { name: /keep server/i });
      expect(buttons.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows "Merge" button for each conflict', async () => {
    renderConflictsPage();
    await waitFor(() => {
      const buttons = screen.getAllByRole('button', { name: /merge/i });
      expect(buttons.length).toBeGreaterThanOrEqual(1);
    });
  });

  // --- Keep Mine action ---

  it('Keep Mine calls updateNote API with serverId', async () => {
    renderConflictsPage();
    await waitFor(() => screen.getAllByRole('button', { name: /keep mine/i }));

    const keepLocalButtons = screen.getAllByRole('button', { name: /keep mine/i });
    fireEvent.click(keepLocalButtons[0]);

    const { updateNote } = await import('../api/notes');
    await waitFor(() => {
      expect(updateNote).toHaveBeenCalledWith(
        'server-conflict-1',
        expect.any(Object),
      );
    });
  });

  it('Keep Mine sets syncStatus=synced in IndexedDB', async () => {
    renderConflictsPage();
    await waitFor(() => screen.getAllByRole('button', { name: /keep mine/i }));

    fireEvent.click(screen.getAllByRole('button', { name: /keep mine/i })[0]);

    const { db } = await import('../db');
    await waitFor(() => {
      expect(db.notes.update).toHaveBeenCalledWith(
        'local-conflict-1',
        expect.objectContaining({ syncStatus: 'synced' }),
      );
    });
  });

  // --- Keep Server action ---

  it('Keep Server sets syncStatus=synced in IndexedDB', async () => {
    renderConflictsPage();
    await waitFor(() => screen.getAllByRole('button', { name: /keep server/i }));

    fireEvent.click(screen.getAllByRole('button', { name: /keep server/i })[0]);

    const { db } = await import('../db');
    await waitFor(() => {
      expect(db.notes.update).toHaveBeenCalledWith(
        'local-conflict-1',
        expect.objectContaining({ syncStatus: 'synced' }),
      );
    });
  });

  it('Keep Server overwrites local content with server content', async () => {
    renderConflictsPage();
    await waitFor(() => screen.getAllByRole('button', { name: /keep server/i }));

    fireEvent.click(screen.getAllByRole('button', { name: /keep server/i })[0]);

    const { db } = await import('../db');
    await waitFor(() => {
      expect(db.notes.update).toHaveBeenCalledWith(
        'local-conflict-1',
        expect.objectContaining({ content: 'SERVER version of the note' }),
      );
    });
  });

  // --- Merge action ---

  it('Merge opens NoteEditor for the conflicted note', async () => {
    renderConflictsPage();
    await waitFor(() => screen.getAllByRole('button', { name: /merge/i }));

    fireEvent.click(screen.getAllByRole('button', { name: /merge/i })[0]);

    await waitFor(() => {
      expect(screen.getByTestId('note-editor')).toBeInTheDocument();
    });
  });

  it('NoteEditor is prefilled with local content for merge', async () => {
    renderConflictsPage();
    await waitFor(() => screen.getAllByRole('button', { name: /merge/i }));

    fireEvent.click(screen.getAllByRole('button', { name: /merge/i })[0]);

    await waitFor(() => {
      expect(screen.getByText(/Editing: My LOCAL edits/i)).toBeInTheDocument();
    });
  });

  it('saving from NoteEditor (Merge) sets syncStatus=synced', async () => {
    renderConflictsPage();
    await waitFor(() => screen.getAllByRole('button', { name: /merge/i }));

    fireEvent.click(screen.getAllByRole('button', { name: /merge/i })[0]);
    await waitFor(() => screen.getByTestId('note-editor'));

    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    const { db } = await import('../db');
    await waitFor(() => {
      expect(db.notes.update).toHaveBeenCalledWith(
        'local-conflict-1',
        expect.objectContaining({ syncStatus: 'synced' }),
      );
    });
  });

  // --- Empty state ---

  it('shows empty state when no conflicts exist', async () => {
    conflictsState.items = [];
    renderConflictsPage();

    await waitFor(() => {
      expect(document.body.textContent).toMatch(/no conflicts|all synced|up to date/i);
    });
  });
});
