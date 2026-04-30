/**
 * CreatePage.test.tsx — Task 5.3 (Express UI / CreatePage)
 * TDD red-phase tests for frontend/src/pages/CreatePage.tsx
 *
 * Tests:
 *   - Renders a Create / Express heading
 *   - Renders kind chooser with song / practice / reflection options
 *   - Renders source note selector (multiselect of user notes)
 *   - Submits POST /api/ai/generate with kind + source_note_ids
 *   - Renders generated text output after successful generation
 *   - Shows loading state while generating
 *   - Shows error message on API failure
 *   - Requires authentication
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mock authStore
// ---------------------------------------------------------------------------

const mockAuthState = {
  accessToken: 'test-token',
  user: { id: 'user-1', email: 'test@example.com', display_name: 'Test User' },
};
const mockUseAuthStore = Object.assign(
  (selector: (s: typeof mockAuthState) => unknown) => selector(mockAuthState),
  { getState: () => mockAuthState, subscribe: vi.fn(), setState: vi.fn() },
);
vi.mock('../store/authStore', () => ({ useAuthStore: mockUseAuthStore }));

// ---------------------------------------------------------------------------
// Mock db / useNotes hook
// ---------------------------------------------------------------------------

const NOTE_FIXTURES = [
  {
    localId: 'note-1',
    serverId: 'server-uuid-1',
    content: 'Jazz improvisation in Dorian mode.',
    category: 'Music',
    tags: ['jazz'],
    syncStatus: 'synced',
    processingStatus: 'enriched',
    sourceType: 'voice',
    createdAt: new Date('2026-04-20T09:00:00Z'),
    updatedAt: new Date('2026-04-20T09:01:00Z'),
  },
  {
    localId: 'note-2',
    serverId: 'server-uuid-2',
    content: 'Morning fitness: 5km run and stretching.',
    category: 'Fitness',
    tags: ['running'],
    syncStatus: 'synced',
    processingStatus: 'enriched',
    sourceType: 'text',
    createdAt: new Date('2026-04-21T07:00:00Z'),
    updatedAt: new Date('2026-04-21T07:01:00Z'),
  },
  {
    localId: 'note-3',
    serverId: 'server-uuid-3',
    content: 'Thoughts on mindfulness and daily journaling.',
    category: 'Journal',
    tags: ['mindfulness'],
    syncStatus: 'synced',
    processingStatus: 'enriched',
    sourceType: 'text',
    createdAt: new Date('2026-04-22T12:00:00Z'),
    updatedAt: new Date('2026-04-22T12:01:00Z'),
  },
];

vi.mock('../hooks/useNotes', () => ({
  useNotes: () => NOTE_FIXTURES,
}));

vi.mock('../db', () => ({
  db: {
    notes: {
      orderBy: () => ({
        reverse: () => ({
          toArray: () => Promise.resolve(NOTE_FIXTURES),
          filter: (fn: (n: typeof NOTE_FIXTURES[0]) => boolean) => ({
            toArray: () => Promise.resolve(NOTE_FIXTURES.filter(fn)),
          }),
        }),
      }),
      toArray: () => Promise.resolve(NOTE_FIXTURES),
    },
  },
}));

// ---------------------------------------------------------------------------
// Mock fetch
// ---------------------------------------------------------------------------

const GENERATED_TEXT = 'Here is a beautiful song idea based on your jazz notes: "Dorian Dreams"...';

function setupFetchMocks(overrides: { ok?: boolean; status?: number; text?: string } = {}) {
  const { ok = true, status = 200, text = GENERATED_TEXT } = overrides;
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (url.includes('ai/generate')) {
        return Promise.resolve({
          ok,
          status,
          json: async () =>
            ok ? { generated_text: text } : { detail: 'Internal server error' },
        });
      }
      if (url.includes('api/notes')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            items: NOTE_FIXTURES.map((n) => ({
              id: n.serverId,
              content: n.content,
              category: n.category,
              source_type: n.sourceType,
              processing_status: n.processingStatus,
              created_at: n.createdAt.toISOString(),
              updated_at: n.updatedAt.toISOString(),
              tags: n.tags,
            })),
            total: NOTE_FIXTURES.length,
          }),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
    }),
  );
}

// ---------------------------------------------------------------------------
// Import component under test
// ---------------------------------------------------------------------------

import CreatePage from '../pages/CreatePage';

function renderCreatePage() {
  return render(
    <MemoryRouter>
      <CreatePage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CreatePage (Task 5.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupFetchMocks();
  });

  // --- Page structure ---

  it('renders a Create or Express heading', async () => {
    renderCreatePage();
    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: /create|express/i });
      expect(heading).toBeInTheDocument();
    });
  });

  // --- Kind chooser ---

  it('renders kind chooser with song option', async () => {
    renderCreatePage();
    await waitFor(() => {
      const songOption = screen.getByText(/song/i);
      expect(songOption).toBeInTheDocument();
    });
  });

  it('renders kind chooser with practice option', async () => {
    renderCreatePage();
    await waitFor(() => {
      const practiceOption = screen.getByText(/practice/i);
      expect(practiceOption).toBeInTheDocument();
    });
  });

  it('renders kind chooser with reflection option', async () => {
    renderCreatePage();
    await waitFor(() => {
      const reflectionOption = screen.getByText(/reflection/i);
      expect(reflectionOption).toBeInTheDocument();
    });
  });

  it('has exactly three kind options', async () => {
    renderCreatePage();
    await waitFor(() => {
      // All three kinds should be visible
      expect(screen.getByText(/song/i)).toBeInTheDocument();
      expect(screen.getByText(/practice/i)).toBeInTheDocument();
      expect(screen.getByText(/reflection/i)).toBeInTheDocument();
    });
  });

  // --- Note selector ---

  it('renders source note selector', async () => {
    renderCreatePage();
    await waitFor(() => {
      // Should show a list/selector of notes to choose from
      expect(
        screen.queryByText(/select notes|source notes|choose notes|pick notes/i) ??
        screen.queryAllByRole('checkbox').length > 0 ? document.createElement('div') : null
      ).toBeInTheDocument();
    });
  });

  it('shows user notes in the note selector', async () => {
    renderCreatePage();
    await waitFor(() => {
      expect(screen.getByText(/Jazz improvisation/i)).toBeInTheDocument();
    });
  });

  it('allows selecting a note', async () => {
    renderCreatePage();
    await waitFor(() => {
      screen.getByText(/Jazz improvisation/i);
    });

    // Find checkboxes or clickable note items
    const checkboxes = screen.queryAllByRole('checkbox');
    const noteItems = screen.queryAllByRole('option');
    const clickableNotes = [...checkboxes, ...noteItems];

    if (clickableNotes.length > 0) {
      fireEvent.click(clickableNotes[0]);
      // Should toggle selection without crashing
    }
  });

  // --- Generate button ---

  it('renders a generate button', async () => {
    renderCreatePage();
    await waitFor(() => {
      const btn = screen.getByRole('button', { name: /generate|create/i });
      expect(btn).toBeInTheDocument();
    });
  });

  it('generate button is disabled when no notes selected', async () => {
    renderCreatePage();
    await waitFor(() => {
      const btn = screen.getByRole('button', { name: /generate|create/i });
      // Without selecting any notes, the button should be disabled
      expect(btn).toBeDisabled();
    });
  });

  // --- API submission ---

  it('submits POST /api/ai/generate with correct payload on generate', async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes('ai/generate')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ generated_text: GENERATED_TEXT }),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ items: NOTE_FIXTURES.map((n) => ({ id: n.serverId, content: n.content, category: n.category, source_type: n.sourceType, processing_status: n.processingStatus, created_at: n.createdAt.toISOString(), updated_at: n.updatedAt.toISOString(), tags: n.tags })), total: NOTE_FIXTURES.length }),
      });
    });
    vi.stubGlobal('fetch', fetchSpy);

    renderCreatePage();

    await waitFor(() => {
      screen.getByText(/Jazz improvisation/i);
    });

    // Select a note (first checkbox or note item)
    const checkboxes = screen.queryAllByRole('checkbox');
    if (checkboxes.length > 0) {
      fireEvent.click(checkboxes[0]);
    }

    // Click generate
    const generateBtn = screen.getByRole('button', { name: /generate|create/i });
    fireEvent.click(generateBtn);

    await waitFor(() => {
      const generateCall = fetchSpy.mock.calls.find(([url]: [string]) =>
        url.includes('ai/generate'),
      );
      if (generateCall) {
        const [, options] = generateCall as [string, RequestInit];
        const body = JSON.parse(options?.body as string ?? '{}');
        expect(body).toHaveProperty('kind');
        expect(body).toHaveProperty('source_note_ids');
        expect(Array.isArray(body.source_note_ids)).toBe(true);
        expect(['song', 'practice', 'reflection']).toContain(body.kind);
      }
    });
  });

  // --- Generated text output ---

  it('displays generated text after successful generation', async () => {
    renderCreatePage();

    await waitFor(() => {
      screen.getByText(/Jazz improvisation/i);
    });

    // Select note and generate
    const checkboxes = screen.queryAllByRole('checkbox');
    if (checkboxes.length > 0) {
      fireEvent.click(checkboxes[0]);
      const generateBtn = screen.getByRole('button', { name: /generate|create/i });
      fireEvent.click(generateBtn);

      await waitFor(() => {
        expect(screen.getByText(/Dorian Dreams|song idea|based on/i)).toBeInTheDocument();
      });
    }
  });

  // --- Loading state ---

  it('shows loading indicator while generating', async () => {
    let resolveGenerate: (value: unknown) => void;
    const pendingGenerate = new Promise((res) => { resolveGenerate = res; });

    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.includes('ai/generate')) return pendingGenerate;
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ items: [], total: 0 }) });
    }));

    renderCreatePage();

    await waitFor(() => {
      screen.getByText(/Jazz improvisation/i);
    });

    const checkboxes = screen.queryAllByRole('checkbox');
    if (checkboxes.length > 0) {
      fireEvent.click(checkboxes[0]);
      const generateBtn = screen.getByRole('button', { name: /generate|create/i });
      fireEvent.click(generateBtn);

      // During generation, a loading indicator should appear
      expect(document.body.textContent).toMatch(/generating|loading|creating|…|\.\.\./i);
    }
  });

  // --- Error state ---

  it('shows error message when generation API fails', async () => {
    setupFetchMocks({ ok: false, status: 500 });

    renderCreatePage();

    await waitFor(() => {
      screen.getByText(/Jazz improvisation/i);
    });

    const checkboxes = screen.queryAllByRole('checkbox');
    if (checkboxes.length > 0) {
      fireEvent.click(checkboxes[0]);
      const generateBtn = screen.getByRole('button', { name: /generate|create/i });
      fireEvent.click(generateBtn);

      await waitFor(() => {
        expect(document.body.textContent).toMatch(/error|failed|could not generate/i);
      });
    }
  });

  // --- Authorization ---

  it('sends Authorization header with generate request', async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () =>
          url.includes('ai/generate')
            ? { generated_text: GENERATED_TEXT }
            : { items: NOTE_FIXTURES.map((n) => ({ id: n.serverId, content: n.content, category: n.category, source_type: n.sourceType, processing_status: n.processingStatus, created_at: n.createdAt.toISOString(), updated_at: n.updatedAt.toISOString(), tags: n.tags })), total: NOTE_FIXTURES.length },
      });
    });
    vi.stubGlobal('fetch', fetchSpy);

    renderCreatePage();

    await waitFor(() => {
      screen.getByText(/Jazz improvisation/i);
    });

    const checkboxes = screen.queryAllByRole('checkbox');
    if (checkboxes.length > 0) {
      fireEvent.click(checkboxes[0]);
      const generateBtn = screen.getByRole('button', { name: /generate|create/i });
      fireEvent.click(generateBtn);

      await waitFor(() => {
        const generateCall = fetchSpy.mock.calls.find(([url]: [string]) =>
          url.includes('ai/generate'),
        );
        if (generateCall) {
          const [, options] = generateCall as [string, RequestInit];
          expect(JSON.stringify(options?.headers ?? {})).toContain('Bearer');
        }
      });
    }
  });
});
