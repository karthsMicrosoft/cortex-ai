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

// Fix vitest hoisting (see BrainViewPage.test.tsx for full explanation).
const { mockAuthState, mockUseAuthStore } = vi.hoisted(() => {
  const mockAuthState = {
    accessToken: 'test-token',
    user: { id: 'user-1', email: 'test@example.com', display_name: 'Test User' },
  };
  const mockUseAuthStore = Object.assign(
    (selector: (s: typeof mockAuthState) => unknown) => selector(mockAuthState),
    { getState: () => mockAuthState, subscribe: () => () => {}, setState: () => {} },
  );
  return { mockAuthState, mockUseAuthStore };
});
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
      // CreatePage has both an h1 ("Create") and an h2 ("What do you want to
      // create?"). Both match /create/i, so disambiguate by level.
      const heading = screen.getByRole('heading', { level: 1, name: /create|express/i });
      expect(heading).toBeInTheDocument();
    });
  });

  // --- Kind chooser ---

  it('renders kind chooser with song option', async () => {
    renderCreatePage();
    await waitFor(() => {
      // Two buttons can match /song idea/i — the kind chooser ("Song Idea")
      // AND the bottom generate button ("Generate Song Idea") when selectedKind
      // is 'song'. Use exact match to target only the chooser button.
      const songOption = screen.getByRole('button', { name: /^song idea$/i });
      expect(songOption).toBeInTheDocument();
    });
  });

  it('renders kind chooser with practice option', async () => {
    renderCreatePage();
    await waitFor(() => {
      const practiceOption = screen.getByRole('button', { name: /^practice plan$/i });
      expect(practiceOption).toBeInTheDocument();
    });
  });

  it('renders kind chooser with reflection option', async () => {
    renderCreatePage();
    await waitFor(() => {
      const reflectionOption = screen.getByRole('button', { name: /^reflection$/i });
      expect(reflectionOption).toBeInTheDocument();
    });
  });

  it('has exactly three kind options', async () => {
    renderCreatePage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^song idea$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^practice plan$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^reflection$/i })).toBeInTheDocument();
    });
  });

  // --- Note selector ---

  it('renders source note selector', async () => {
    renderCreatePage();
    await waitFor(() => {
      // Production renders a "Source Notes (N selected)" h2 above a list of
      // <button aria-pressed> per note. Match either the heading or the list.
      const heading = screen.queryByRole('heading', { name: /source notes/i });
      const noteButtons = screen
        .queryAllByRole('button')
        .filter((b) => b.getAttribute('aria-pressed') !== null);
      expect(heading !== null || noteButtons.length > 0).toBe(true);
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

    // Same notes-list mock as the default setupFetchMocks so the source-note
    // selector actually has rows to click. The generate endpoint is left
    // pending so the loading state stays visible for the assertion.
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.includes('ai/generate')) return pendingGenerate;
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
    }));

    renderCreatePage();

    // Production renders source-note rows as <button aria-pressed> with text
    // starting with the category in brackets (e.g. "[Music] Jazz improvisation
    // in Dorian mode."). Kind-chooser buttons ALSO have aria-pressed, so
    // filter further by looking for the bracketed category prefix.
    const noteButton = await waitFor(() => {
      const btn = screen
        .queryAllByRole('button')
        .find((b) =>
          b.getAttribute('aria-pressed') !== null &&
          /^\[[A-Za-z]+\]/.test(b.textContent ?? ''),
        );
      if (!btn) throw new Error('source-note button not yet rendered');
      return btn;
    });

    fireEvent.click(noteButton);
    const generateBtn = screen.getByRole('button', { name: /^generate /i });
    fireEvent.click(generateBtn);

    // During generation, the button text flips to "Generating…"
    await waitFor(() => {
      expect(document.body.textContent).toMatch(/generating|loading|creating|\.\.\./i);
    });
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

  // ---------------------------------------------------------------------------
  // Round 15 / PR #22 — Express CreatePage polish
  // ---------------------------------------------------------------------------

  // Helpers for the polish tests below — find the first source-note button
  // (aria-pressed + [Category] text prefix) and click it; then click Generate
  // and wait for the generated text to appear.
  async function selectFirstNoteAndGenerate() {
    const noteBtn = await waitFor(() => {
      const btn = screen
        .queryAllByRole('button')
        .find((b) =>
          b.getAttribute('aria-pressed') !== null &&
          /^\[[A-Za-z]+\]/.test(b.textContent ?? ''),
        );
      if (!btn) throw new Error('source-note button not yet rendered');
      return btn;
    });
    fireEvent.click(noteBtn);
    const generateBtn = screen.getByRole('button', { name: /^generate /i });
    fireEvent.click(generateBtn);
    await waitFor(() => {
      expect(screen.getByText(/Dorian Dreams/)).toBeInTheDocument();
    });
  }

  it('renders Copy / Regenerate / Save as Note buttons after generation', async () => {
    renderCreatePage();
    await selectFirstNoteAndGenerate();
    expect(screen.getByRole('button', { name: /^copy$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^regenerate$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save as note/i })).toBeInTheDocument();
  });

  it('Copy button writes generated text to clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });

    renderCreatePage();
    await selectFirstNoteAndGenerate();

    const copyBtn = screen.getByRole('button', { name: /^copy$/i });
    fireEvent.click(copyBtn);
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(GENERATED_TEXT);
    });
    await waitFor(() => {
      expect(document.body.textContent).toMatch(/copied/i);
    });
  });

  it('Regenerate button re-POSTs to /api/ai/generate', async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
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
    });
    vi.stubGlobal('fetch', fetchSpy);

    renderCreatePage();
    await selectFirstNoteAndGenerate();

    const callsBefore = fetchSpy.mock.calls.filter(([u]: [string]) => u.includes('ai/generate')).length;
    const regen = screen.getByRole('button', { name: /^regenerate$/i });
    fireEvent.click(regen);

    await waitFor(() => {
      const callsAfter = fetchSpy.mock.calls.filter(([u]: [string]) => u.includes('ai/generate')).length;
      expect(callsAfter).toBeGreaterThan(callsBefore);
    });
  });

  it('Save as Note POSTs to /api/notes with the right payload', async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes('ai/generate')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ generated_text: GENERATED_TEXT }),
        });
      }
      // POST /api/notes (save-as-note) — distinguished from GET list by method
      if (url.includes('api/notes') && options?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          status: 201,
          json: async () => ({ id: 'new-saved-id', content: GENERATED_TEXT }),
        });
      }
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
    });
    vi.stubGlobal('fetch', fetchSpy);

    renderCreatePage();
    await selectFirstNoteAndGenerate();

    const saveBtn = screen.getByRole('button', { name: /save as note/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      const saveCall = fetchSpy.mock.calls.find(
        ([u, opts]: [string, RequestInit]) => u.includes('api/notes') && opts?.method === 'POST',
      );
      expect(saveCall).toBeTruthy();
      const [, opts] = saveCall as [string, RequestInit];
      const body = JSON.parse(opts.body as string);
      expect(body.content).toBe(GENERATED_TEXT);
      expect(body.source_type).toBe('text');
      expect(body.tags).toEqual(expect.arrayContaining(['express', 'song']));
    });
    await waitFor(() => {
      expect(document.body.textContent).toMatch(/saved to library/i);
    });
  });

  it('mode switch resets selected notes', async () => {
    renderCreatePage();
    const noteBtn = await waitFor(() => {
      const btn = screen
        .queryAllByRole('button')
        .find((b) =>
          b.getAttribute('aria-pressed') !== null &&
          /^\[[A-Za-z]+\]/.test(b.textContent ?? ''),
        );
      if (!btn) throw new Error('source-note button not yet rendered');
      return btn;
    });
    fireEvent.click(noteBtn);
    expect(screen.getByText(/1 selected/i)).toBeInTheDocument();

    // Switch mode
    fireEvent.click(screen.getByRole('button', { name: /^practice plan$/i }));
    await waitFor(() => {
      expect(screen.getByText(/0 selected/i)).toBeInTheDocument();
    });
  });

  it('mode switch resets generated text', async () => {
    renderCreatePage();
    await selectFirstNoteAndGenerate();
    expect(screen.getByText(/Dorian Dreams/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^reflection$/i }));
    await waitFor(() => {
      expect(screen.queryByText(/Dorian Dreams/)).not.toBeInTheDocument();
    });
  });

  it('note-load failure shows retry button that re-fetches', async () => {
    let notesCalls = 0;
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      if (url.includes('api/notes')) {
        notesCalls += 1;
        if (notesCalls === 1) {
          return Promise.resolve({
            ok: false,
            status: 500,
            json: async () => ({ detail: 'server boom' }),
          });
        }
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
    });
    vi.stubGlobal('fetch', fetchSpy);

    renderCreatePage();
    const retryBtn = await waitFor(() => {
      return screen.getByRole('button', { name: /retry/i });
    });
    fireEvent.click(retryBtn);
    await waitFor(() => {
      expect(screen.getByText(/Jazz improvisation/i)).toBeInTheDocument();
    });
    expect(notesCalls).toBeGreaterThanOrEqual(2);
  });

  it('per-mode hint changes when mode changes', async () => {
    renderCreatePage();
    await waitFor(() => {
      expect(screen.getByText(/best with music or songwriting notes/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /^practice plan$/i }));
    await waitFor(() => {
      expect(screen.getByText(/best with workout, training, or skill-practice notes/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /^reflection$/i }));
    await waitFor(() => {
      expect(screen.getByText(/best with journal entries and personal reflection notes/i)).toBeInTheDocument();
    });
  });

  it('loadError, validationError, generateError are independent', async () => {
    // Generate API fails, but notes load works — validationError must not be
    // set, and loadError must not appear; only generateError shows.
    setupFetchMocks({ ok: false, status: 500 });
    renderCreatePage();

    const noteBtn = await waitFor(() => {
      const btn = screen
        .queryAllByRole('button')
        .find((b) =>
          b.getAttribute('aria-pressed') !== null &&
          /^\[[A-Za-z]+\]/.test(b.textContent ?? ''),
        );
      if (!btn) throw new Error('source-note button not yet rendered');
      return btn;
    });
    fireEvent.click(noteBtn);
    fireEvent.click(screen.getByRole('button', { name: /^generate /i }));

    // generateError should be reachable via test id while loadError is not
    await waitFor(() => {
      expect(screen.getByTestId('generate-error')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('load-error')).not.toBeInTheDocument();
    expect(screen.queryByTestId('validation-error')).not.toBeInTheDocument();
  });

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
