/**
 * Task 2.3 — NoteEditor — TDD red
 *
 * Tests that `frontend/src/components/NoteEditor.tsx`:
 *   - Renders editable content field
 *   - Renders a six-option category dropdown (Music, Fitness, Journal, Ideas, Spiritual, Learning)
 *   - Renders tag chips with add (Enter) and remove (X) controls
 *   - Renders a mood field (free-text or dropdown)
 *   - When category='Music', renders music_metadata quick-edit chips
 *     (tempo, key, genre, instruments)
 *   - Shows "AI-suggested" badge on each AI-populated field until the user edits it
 *   - On save, calls onSave with only changed fields (NoteUpdate shape)
 *   - Manual edits to category/tags/mood/music_metadata do NOT change processingStatus to 'raw'
 *     (pipeline re-run is only triggered by content change — mitigation #6)
 *
 * Critical: B8 resolution — this is a first-class UX requirement.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// ---------------------------------------------------------------------------
// userEvent may not be installed; fall back gracefully
// ---------------------------------------------------------------------------

// Mock fetch for PUT /api/notes/{id}
const mockFetch = vi.fn().mockResolvedValue({
  ok: true,
  json: async () => ({ id: 'server-id', content: 'updated' }),
});
vi.stubGlobal('fetch', mockFetch);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const baseNote = {
  localId: 'note-abc',
  serverId: 'server-abc',
  content: 'This is the original note content.',
  sourceType: 'voice' as const,
  category: 'Ideas' as const,
  tags: ['productivity', 'work'],
  mood: 'focused',
  music_metadata: {},
  syncStatus: 'synced' as const,
  processingStatus: 'enriched' as const,
  aiSuggestedFields: ['category', 'tags', 'mood'],
  createdAt: new Date(),
  updatedAt: new Date(),
};

const musicNote = {
  ...baseNote,
  category: 'Music' as const,
  music_metadata: {
    tempo: '120 BPM',
    key: 'C major',
    genre: 'Jazz',
    instruments: 'Guitar, Bass',
  },
  aiSuggestedFields: ['category', 'tags', 'mood', 'music_metadata'],
};

// ---------------------------------------------------------------------------
// Import component under test
// ---------------------------------------------------------------------------

import { NoteEditor } from '../components/NoteEditor';

function renderEditor(
  note: typeof baseNote = baseNote,
  onSave: (patch: Record<string, unknown>) => Promise<void> = vi.fn().mockResolvedValue(undefined),
  onCancel?: () => void,
) {
  return render(
    <NoteEditor note={note} onSave={onSave} onCancel={onCancel ?? vi.fn()} />,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('NoteEditor (Task 2.3 — B8 manual override)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --- Content field ---

  it('renders a content textarea/editor', () => {
    renderEditor();
    // Should have at least one text field pre-filled with note content
    const textarea = screen.getByDisplayValue(/original note content/i);
    expect(textarea).toBeInTheDocument();
  });

  // --- Category dropdown (six fixed values) ---

  it('renders a category dropdown', () => {
    renderEditor();
    const select = screen.getByRole('combobox', { name: /category/i });
    expect(select).toBeInTheDocument();
  });

  it('category dropdown has exactly six options', () => {
    renderEditor();
    const select = screen.getByRole('combobox', { name: /category/i });
    const options = Array.from((select as HTMLSelectElement).options);
    const validValues = ['Music', 'Fitness', 'Journal', 'Ideas', 'Spiritual', 'Learning'];
    const optionValues = options.map((o) => o.value).filter((v) => validValues.includes(v));
    expect(optionValues).toHaveLength(6);
  });

  it('category dropdown includes all six valid categories', () => {
    renderEditor();
    const select = screen.getByRole('combobox', { name: /category/i });
    const options = Array.from((select as HTMLSelectElement).options).map((o) => o.value);
    expect(options).toContain('Music');
    expect(options).toContain('Fitness');
    expect(options).toContain('Journal');
    expect(options).toContain('Ideas');
    expect(options).toContain('Spiritual');
    expect(options).toContain('Learning');
  });

  it('category dropdown shows current note category as selected', () => {
    renderEditor();
    const select = screen.getByRole('combobox', { name: /category/i }) as HTMLSelectElement;
    expect(select.value).toBe('Ideas');
  });

  // --- Tags chips (add + remove) ---

  it('renders existing tags as chips', () => {
    renderEditor();
    expect(screen.getByText('productivity')).toBeInTheDocument();
    expect(screen.getByText('work')).toBeInTheDocument();
  });

  it('each tag chip has a remove button (X)', () => {
    renderEditor();
    // There should be remove buttons for each tag
    const removeButtons = screen.getAllByRole('button', { name: /remove|delete|×|x/i });
    expect(removeButtons.length).toBeGreaterThanOrEqual(2);
  });

  it('removing a tag removes it from the visible list', async () => {
    renderEditor();
    const removeButtons = screen.getAllByRole('button', { name: /remove|delete|×|x/i });
    fireEvent.click(removeButtons[0]);
    await waitFor(() => {
      // One of the original tags should be gone
      const tags = screen.queryAllByText(/productivity|work/i);
      expect(tags.length).toBeLessThan(2);
    });
  });

  it('renders a tag input for adding new tags', () => {
    renderEditor();
    const tagInput = screen.getByPlaceholderText(/add tag|new tag|tag/i);
    expect(tagInput).toBeInTheDocument();
  });

  it('pressing Enter in tag input adds a new tag', async () => {
    renderEditor();
    const tagInput = screen.getByPlaceholderText(/add tag|new tag|tag/i);
    fireEvent.change(tagInput, { target: { value: 'newtag' } });
    fireEvent.keyDown(tagInput, { key: 'Enter', code: 'Enter' });
    await waitFor(() => {
      expect(screen.getByText('newtag')).toBeInTheDocument();
    });
  });

  // --- Mood field ---

  it('renders a mood input field', () => {
    renderEditor();
    const moodInput = screen.getByLabelText(/mood/i);
    expect(moodInput).toBeInTheDocument();
  });

  it('mood input shows current mood value', () => {
    renderEditor();
    const moodInput = screen.getByLabelText(/mood/i) as HTMLInputElement;
    expect(moodInput.value).toBe('focused');
  });

  // --- Music metadata (only when category='Music') ---

  it('does NOT render music_metadata chips when category is not Music', () => {
    renderEditor(); // category='Ideas'
    expect(screen.queryByTestId('music-metadata')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/tempo/i)).not.toBeInTheDocument();
  });

  it('renders music_metadata section when category=Music', () => {
    renderEditor(musicNote);
    expect(screen.getByTestId('music-metadata')).toBeInTheDocument();
  });

  it('music_metadata section shows tempo chip', () => {
    renderEditor(musicNote);
    expect(screen.getByText(/120 BPM|tempo/i)).toBeInTheDocument();
  });

  it('music_metadata section shows key chip', () => {
    renderEditor(musicNote);
    expect(screen.getByText(/C major|key/i)).toBeInTheDocument();
  });

  it('music_metadata section shows genre chip', () => {
    renderEditor(musicNote);
    expect(screen.getByText(/Jazz|genre/i)).toBeInTheDocument();
  });

  it('music_metadata section shows instruments chip', () => {
    renderEditor(musicNote);
    expect(screen.getByText(/Guitar.*Bass|instruments/i)).toBeInTheDocument();
  });

  it('switching category dropdown from Ideas to Music reveals music_metadata section', async () => {
    renderEditor();
    expect(screen.queryByTestId('music-metadata')).not.toBeInTheDocument();

    const select = screen.getByRole('combobox', { name: /category/i });
    fireEvent.change(select, { target: { value: 'Music' } });

    await waitFor(() => {
      expect(screen.getByTestId('music-metadata')).toBeInTheDocument();
    });
  });

  // --- AI-suggested badge (B8) ---

  it('shows AI-suggested badge next to category when it is AI-populated', () => {
    renderEditor();
    // aiSuggestedFields includes 'category'
    const badges = screen.getAllByText(/ai.suggested|ai suggested/i);
    expect(badges.length).toBeGreaterThan(0);
  });

  it('AI-suggested badge disappears from category after user changes it', async () => {
    renderEditor();
    const initialBadges = screen.getAllByText(/ai.suggested|ai suggested/i).length;

    const select = screen.getByRole('combobox', { name: /category/i });
    fireEvent.change(select, { target: { value: 'Fitness' } });

    await waitFor(() => {
      const currentBadges = screen.queryAllByText(/ai.suggested|ai suggested/i).length;
      expect(currentBadges).toBeLessThan(initialBadges);
    });
  });

  it('AI-suggested badge disappears from mood after user edits it', async () => {
    renderEditor();
    const initialBadges = screen.getAllByText(/ai.suggested|ai suggested/i).length;

    const moodInput = screen.getByLabelText(/mood/i);
    fireEvent.change(moodInput, { target: { value: 'energetic' } });

    await waitFor(() => {
      const currentBadges = screen.queryAllByText(/ai.suggested|ai suggested/i).length;
      expect(currentBadges).toBeLessThan(initialBadges);
    });
  });

  // --- Save: only changed fields (B8 NoteUpdate shape) ---

  it('renders a Save button', () => {
    renderEditor();
    expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
  });

  it('onSave is called when Save is clicked', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderEditor(baseNote, onSave);
    fireEvent.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
  });

  it('onSave receives only changed fields (exclude_unset semantics)', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderEditor(baseNote, onSave);

    // Only change mood
    const moodInput = screen.getByLabelText(/mood/i);
    fireEvent.change(moodInput, { target: { value: 'energetic' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const patch = onSave.mock.calls[0][0];
    expect(patch.mood).toBe('energetic');
    // content should NOT be in the patch since it wasn't changed
    expect(patch.content).toBeUndefined();
  });

  it('changing category does NOT set processingStatus=raw in the patch (mitigation #6)', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderEditor(baseNote, onSave);

    const select = screen.getByRole('combobox', { name: /category/i });
    fireEvent.change(select, { target: { value: 'Fitness' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const patch = onSave.mock.calls[0][0];
    expect(patch.processing_status).toBeUndefined();
    expect(patch.processingStatus).toBeUndefined();
  });

  it('changing content does trigger content field in patch', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderEditor(baseNote, onSave);

    const textarea = screen.getByDisplayValue(/original note content/i);
    fireEvent.change(textarea, { target: { value: 'New content here' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const patch = onSave.mock.calls[0][0];
    expect(patch.content).toBe('New content here');
  });

  // --- Cancel ---

  it('renders a Cancel button', () => {
    renderEditor();
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
  });

  it('onCancel is called when Cancel is clicked', () => {
    const onCancel = vi.fn();
    renderEditor(baseNote, vi.fn(), onCancel);
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalled();
  });
});
