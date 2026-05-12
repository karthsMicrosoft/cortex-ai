/**
 * Phase 5 / PR 5.1 — SharePage tests
 *
 * /share is a PUBLIC route landed on after the user picks Cortex from the OS
 * share sheet. Manifest delivers the payload as URL params (?title=&text=&url=).
 *
 *   • Authed + URL-only       → POST /api/import/url, navigate to library/note
 *   • Authed + text(+url)     → POST /api/notes, navigate to library/note
 *   • Unauthed                → enqueue payload, redirect to /login
 *   • Failed save             → show error + retry
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// --- Auth store mock (LoginPage-style: hook + getState) ---
const _shareAuthState: {
  accessToken: string | null;
  user: unknown;
  login: ReturnType<typeof vi.fn>;
  logout: ReturnType<typeof vi.fn>;
  setAccessToken: ReturnType<typeof vi.fn>;
} = {
  accessToken: null,
  user: null,
  login: vi.fn(),
  logout: vi.fn(),
  setAccessToken: vi.fn(),
};
vi.mock('../store/authStore', () => ({
  useAuthStore: Object.assign(
    vi.fn((selector?: (s: typeof _shareAuthState) => unknown) =>
      selector ? selector(_shareAuthState) : _shareAuthState,
    ),
    {
      getState: () => _shareAuthState,
      subscribe: () => () => {},
      setState: () => {},
    },
  ),
}));

// --- API mocks ---
vi.mock('../api/notes', () => ({
  createNote: vi.fn(),
}));
vi.mock('../api/import', () => ({
  importUrl: vi.fn(),
}));

// --- shareInbox mock ---
vi.mock('../services/shareInbox', () => ({
  enqueue: vi.fn().mockResolvedValue(undefined),
  drain: vi.fn().mockResolvedValue(0),
  peek: vi.fn().mockResolvedValue(null),
  composeNoteBody: (p: { title?: string; text?: string; url?: string }) =>
    [p.title, p.text, p.url].filter(Boolean).join('\n\n').trim(),
}));

import SharePage from '../pages/SharePage';
import { createNote } from '../api/notes';
import { importUrl } from '../api/import';
import * as shareInbox from '../services/shareInbox';

function setAuthed(token: string | null) {
  _shareAuthState.accessToken = token;
  _shareAuthState.user = token ? { id: 'u1', email: 'a@b.c' } : null;
}

function renderAt(search: string) {
  return render(
    <MemoryRouter initialEntries={[`/share${search}`]}>
      <Routes>
        <Route path="/share" element={<SharePage />} />
        <Route path="/login" element={<div data-testid="login-page">Login</div>} />
        <Route path="/library" element={<div data-testid="library-page">Library</div>} />
        <Route path="/note/:id" element={<div data-testid="note-page">Note</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  setAuthed(null);
});

describe('SharePage — initial render', () => {
  it('renders a Saving indicator on mount when there is a payload', () => {
    setAuthed('tok');
    vi.mocked(importUrl).mockReturnValue(new Promise(() => {})); // never resolves
    renderAt('?url=https%3A%2F%2Fexample.com');
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});

describe('SharePage — authenticated user', () => {
  beforeEach(() => setAuthed('tok'));

  it('URL-only payload calls /api/import/url', async () => {
    vi.mocked(importUrl).mockResolvedValueOnce({ id: 'note-1' } as never);
    renderAt('?url=https%3A%2F%2Fexample.com%2Farticle');
    await waitFor(() => {
      expect(importUrl).toHaveBeenCalledWith({
        url: 'https://example.com/article',
        title: undefined,
      });
    });
  });

  it('text-only payload calls /api/notes', async () => {
    vi.mocked(createNote).mockResolvedValueOnce({ id: 'note-2' } as never);
    renderAt('?text=A%20quick%20thought');
    await waitFor(() => {
      expect(createNote).toHaveBeenCalledWith(
        expect.objectContaining({
          content: expect.stringContaining('A quick thought'),
          source_type: 'text',
        }),
      );
    });
  });

  it('text + url payload combines body and URL into a single note', async () => {
    vi.mocked(createNote).mockResolvedValueOnce({ id: 'note-3' } as never);
    renderAt('?text=Look%20at%20this&url=https%3A%2F%2Fexample.com%2Fx');
    await waitFor(() => {
      expect(createNote).toHaveBeenCalledTimes(1);
    });
    const arg = vi.mocked(createNote).mock.calls[0][0];
    expect(arg.content).toContain('Look at this');
    expect(arg.content).toContain('https://example.com/x');
  });

  it('navigates to /library after successful save', async () => {
    vi.mocked(importUrl).mockResolvedValueOnce({ id: 'lib-1' } as never);
    renderAt('?url=https%3A%2F%2Fexample.com');
    await waitFor(() => {
      expect(screen.getByTestId('library-page')).toBeInTheDocument();
    });
  });

  it('shows error UI and retry button when import fails', async () => {
    vi.mocked(importUrl).mockRejectedValueOnce(new Error('Boom'));
    renderAt('?url=https%3A%2F%2Fexample.com');
    await waitFor(() => {
      const text = (document.body.textContent ?? '').toLowerCase();
      expect(text).toMatch(/error|failed|retry|try again/);
    });
    expect(screen.getByRole('button', { name: /retry|try again/i })).toBeInTheDocument();
  });

  it('does not enqueue to share inbox when authenticated', async () => {
    vi.mocked(importUrl).mockResolvedValueOnce({ id: 'x' } as never);
    renderAt('?url=https%3A%2F%2Fexample.com');
    await waitFor(() => {
      expect(importUrl).toHaveBeenCalled();
    });
    expect(shareInbox.enqueue).not.toHaveBeenCalled();
  });
});

describe('SharePage — unauthenticated user', () => {
  beforeEach(() => setAuthed(null));

  it('stashes the payload in shared_inbox', async () => {
    renderAt('?url=https%3A%2F%2Fexample.com');
    await waitFor(() => {
      expect(shareInbox.enqueue).toHaveBeenCalledWith(
        expect.objectContaining({ url: 'https://example.com' }),
      );
    });
  });

  it('redirects to /login', async () => {
    renderAt('?text=hi');
    await waitFor(() => {
      expect(screen.getByTestId('login-page')).toBeInTheDocument();
    });
  });

  it('does not call /api/notes or /api/import/url', async () => {
    renderAt('?text=hello&url=https%3A%2F%2Fa.test');
    await waitFor(() => {
      expect(shareInbox.enqueue).toHaveBeenCalled();
    });
    expect(createNote).not.toHaveBeenCalled();
    expect(importUrl).not.toHaveBeenCalled();
  });
});

describe('SharePage — empty payload', () => {
  it('shows an empty-state message when no params are present', async () => {
    setAuthed('tok');
    renderAt('');
    await waitFor(() => {
      const text = (document.body.textContent ?? '').toLowerCase();
      expect(text).toMatch(/nothing to share|no content|empty/);
    });
    expect(createNote).not.toHaveBeenCalled();
    expect(importUrl).not.toHaveBeenCalled();
  });
});
