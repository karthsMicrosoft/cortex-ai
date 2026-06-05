import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockDbState = vi.hoisted(() => {
  const notes = new Map<string, Record<string, unknown>>();
  let queue: Array<Record<string, unknown> & { id: number; entityId: string }> = [];
  let nextQueueId = 1;

  const notesAdd = vi.fn(async (note: Record<string, unknown> & { localId: string }) => {
    notes.set(note.localId, note);
    return note.localId;
  });
  const notesGet = vi.fn(async (id: string) => notes.get(id));
  const notesUpdate = vi.fn(async (id: string, changes: Record<string, unknown>) => {
    notes.set(id, { ...(notes.get(id) ?? {}), ...changes });
    return 1;
  });
  const syncQueueAdd = vi.fn(async (op: Record<string, unknown> & { entityId: string }) => {
    const id = nextQueueId++;
    queue.push({ ...op, id });
    return id;
  });
  const syncQueueDelete = vi.fn(async (id: number) => {
    queue = queue.filter((item) => item.id !== id);
  });

  return {
    notesAdd,
    notesGet,
    notesUpdate,
    syncQueueAdd,
    syncQueueDelete,
    orderBy: vi.fn(() => ({ toArray: vi.fn(async () => [...queue]) })),
    reset: () => {
      notes.clear();
      queue = [];
      nextQueueId = 1;
      notesAdd.mockClear();
      notesGet.mockClear();
      notesUpdate.mockClear();
      syncQueueAdd.mockClear();
      syncQueueDelete.mockClear();
    },
  };
});

const { fetchMock } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
}));

vi.mock('../db', () => ({
  db: {
    notes: {
      add: mockDbState.notesAdd,
      get: mockDbState.notesGet,
      update: mockDbState.notesUpdate,
    },
    syncQueue: {
      add: mockDbState.syncQueueAdd,
      orderBy: mockDbState.orderBy,
      delete: mockDbState.syncQueueDelete,
    },
    deadLetter: { add: vi.fn() },
  },
}));

vi.mock('../api/client', () => ({
  apiUrl: (path: string) => path,
}));

const { mockUseAuthStore } = vi.hoisted(() => {
  const state = { accessToken: 'test-token', user: null };
  return {
    mockUseAuthStore: Object.assign(
      (selector: (storeState: typeof state) => unknown) => selector(state),
      { getState: () => state, subscribe: () => () => {}, setState: () => {} },
    ),
  };
});
vi.mock('../store/authStore', () => ({ useAuthStore: mockUseAuthStore }));

vi.mock('../components/VoiceCapture', async () => {
  const React = await import('react');
  return {
    VoiceCapture: React.forwardRef(function MockVoiceCapture(
      _props: { onNoteCreated?: (id: string) => void },
      ref: React.ForwardedRef<{ start: () => void }>,
    ) {
      React.useImperativeHandle(ref, () => ({ start: vi.fn() }));
      return React.createElement('div', { 'data-testid': 'voice-capture-fab' }, 'Voice FAB');
    }),
  };
});

vi.mock('../components/SyncIndicator', () => ({
  SyncIndicator: () => <div data-testid="sync-indicator" />,
}));

vi.mock('../components/UrlClipForm', () => ({
  UrlClipForm: () => <div data-testid="url-clip-form" />,
}));

vi.mock('uuid', () => ({
  v4: () => 'deadline-hint-id',
}));

import { CapturePage } from '../pages/CapturePage';

function renderCapturePage() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<CapturePage />} />
        <Route path="/library" element={<div data-testid="library-page" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('CapturePage deadline hints', () => {
  beforeEach(() => {
    mockDbState.reset();
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 'server-note-1',
          content: 'Submit expense by tomorrow #high',
          processing_status: 'raw',
          updated_at: new Date().toISOString(),
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
    globalThis.fetch = fetchMock as typeof fetch;
  });

  it('previews and POSTs extracted deadline hints', async () => {
    renderCapturePage();

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'Submit expense by tomorrow #high' },
    });

    await waitFor(() => {
      expect(screen.getByTestId('deadline-pill-preview')).toHaveTextContent(/Tomorrow/i);
    });

    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const notePostCall = fetchMock.mock.calls.find((call) => call[0] === '/api/notes');
    expect(notePostCall).toBeTruthy();

    const body = JSON.parse(String((notePostCall?.[1] as RequestInit).body)) as Record<string, unknown>;
    expect(new Date(String(body.due_at_hint)).getTime()).toBeGreaterThan(Date.now());
    expect(body.priority_hint).toBe(1);
    expect(body).not.toHaveProperty('recurring_hint');
  });
});
