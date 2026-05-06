/**
 * PersonalDictionary.test.tsx — US-7 (TDD red phase)
 *
 * Tests for frontend/src/components/PersonalDictionary.tsx
 *
 * Covers:
 *   - Component renders without crashing
 *   - Chip list renders fetched terms
 *   - TYPE_COLORS mapping applied to each chip (bg-blue-900, bg-purple-900, etc.)
 *   - Type selector dropdown present with all 6 type options
 *   - Text input present with placeholder
 *   - Add button present
 *   - Enter key in input calls add
 *   - Clicking X on a chip calls deleteTerm
 *   - 400 error displayed as limit message
 *   - 409 error displayed as duplicate message
 *   - Type filter controls the displayed list
 *
 * Design refs:
 *   - SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md § F1.2 (Frontend: Personal Dictionary UI)
 *   - us-7-personal-dictionary.tasks.md task 4.2
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import React from 'react';

// ---------------------------------------------------------------------------
// Mock the dictionary API module (not yet implemented — red phase)
// ---------------------------------------------------------------------------

const mockListTerms = vi.fn();
const mockAddTerm = vi.fn();
const mockDeleteTerm = vi.fn();
const mockUpdateTerm = vi.fn();
const mockBulkImport = vi.fn();
const mockExportTerms = vi.fn();

vi.mock('../api/dictionary', () => ({
  listTerms: (...args: unknown[]) => mockListTerms(...args),
  addTerm: (...args: unknown[]) => mockAddTerm(...args),
  deleteTerm: (...args: unknown[]) => mockDeleteTerm(...args),
  updateTerm: (...args: unknown[]) => mockUpdateTerm(...args),
  bulkImport: (...args: unknown[]) => mockBulkImport(...args),
  exportTerms: (...args: unknown[]) => mockExportTerms(...args),
}));

// ---------------------------------------------------------------------------
// Mock authStore (used by api/client fetchWithAuth)
// ---------------------------------------------------------------------------

vi.mock('../store/authStore', () => {
  const state = { accessToken: 'test-token', user: { id: 'u1' } };
  const store = Object.assign(
    (selector: (s: typeof state) => unknown) => selector(state),
    { getState: () => state, subscribe: () => () => {}, setState: () => {} },
  );
  return { useAuthStore: store };
});

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------

type TermType = 'name' | 'music_term' | 'technical' | 'place' | 'acronym' | 'general';

interface VocabTerm {
  id: string;
  term: string;
  term_type: TermType;
  pronunciation_hint?: string;
  usage_count: number;
}

const SAMPLE_TERMS: VocabTerm[] = [
  { id: 'id-1', term: 'Karthik', term_type: 'name', usage_count: 5 },
  { id: 'id-2', term: 'arpeggio', term_type: 'music_term', usage_count: 3 },
  { id: 'id-3', term: 'pgvector', term_type: 'technical', usage_count: 2 },
  { id: 'id-4', term: 'Seattle', term_type: 'place', usage_count: 1 },
  { id: 'id-5', term: 'CODE', term_type: 'acronym', usage_count: 0 },
  { id: 'id-6', term: 'meeting', term_type: 'general', usage_count: 0 },
];

// TYPE_COLORS from the design spec
const TYPE_COLORS: Record<TermType, string> = {
  name: 'bg-blue-900',
  music_term: 'bg-purple-900',
  technical: 'bg-green-900',
  place: 'bg-amber-900',
  acronym: 'bg-rose-900',
  general: 'bg-slate-700',
};

// ---------------------------------------------------------------------------
// Helper: render the component (fails red until component is created)
// ---------------------------------------------------------------------------

async function renderPersonalDictionary() {
  // Dynamic import so the test file is still *collected* even when the component
  // does not exist yet (collection error would prevent the red signal from being sent).
  const mod = await import('../components/PersonalDictionary');
  const PersonalDictionary = mod.PersonalDictionary ?? mod.default;
  return render(<PersonalDictionary />);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PersonalDictionary component (task 4.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListTerms.mockResolvedValue(SAMPLE_TERMS);
    mockAddTerm.mockResolvedValue({ id: 'new-id', term: 'new', term_type: 'general', usage_count: 0 });
    mockDeleteTerm.mockResolvedValue(undefined);
  });

  // --- Import guard (the very first red signal) ---

  it('PersonalDictionary module is importable', async () => {
    const mod = await import('../components/PersonalDictionary');
    const component = mod.PersonalDictionary ?? mod.default;
    expect(typeof component).toBe('function');
  });

  // --- Render ---

  it('renders without crashing', async () => {
    await renderPersonalDictionary();
    // If we get here the component mounted
    expect(document.body).toBeTruthy();
  });

  it('renders a text input for new terms', async () => {
    await renderPersonalDictionary();
    await waitFor(() => {
      const input = document.querySelector<HTMLInputElement>('input[type="text"]')
        ?? document.querySelector<HTMLInputElement>('input:not([type="hidden"])');
      expect(input).toBeTruthy();
    });
  });

  it('renders an Add button', async () => {
    await renderPersonalDictionary();
    await waitFor(() => {
      // The add button may be identified by role=button or a + icon
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThan(0);
    });
  });

  it('renders a type selector dropdown', async () => {
    await renderPersonalDictionary();
    await waitFor(() => {
      const select = document.querySelector('select');
      expect(select).toBeTruthy();
    });
  });

  // --- Type selector options ---

  it('type selector contains "name" option', async () => {
    await renderPersonalDictionary();
    await waitFor(() => {
      const options = Array.from(document.querySelectorAll('option')).map(
        (o) => o.value.toLowerCase(),
      );
      expect(options).toContain('name');
    });
  });

  it('type selector contains "music_term" option', async () => {
    await renderPersonalDictionary();
    await waitFor(() => {
      const options = Array.from(document.querySelectorAll('option')).map((o) => o.value);
      expect(options).toContain('music_term');
    });
  });

  it('type selector contains all 6 term types', async () => {
    await renderPersonalDictionary();
    await waitFor(() => {
      const options = Array.from(document.querySelectorAll('option')).map((o) => o.value);
      const required = ['name', 'music_term', 'technical', 'place', 'acronym', 'general'];
      for (const type of required) {
        expect(options).toContain(type);
      }
    });
  });

  // --- Chip list ---

  it('fetches and displays all terms as chips', async () => {
    await renderPersonalDictionary();
    await waitFor(() => {
      expect(mockListTerms).toHaveBeenCalled();
    });
    await waitFor(() => {
      for (const term of SAMPLE_TERMS) {
        expect(screen.getByText(term.term)).toBeInTheDocument();
      }
    });
  });

  it('each chip has a delete (X) button', async () => {
    await renderPersonalDictionary();
    await waitFor(() => {
      // There should be one dismiss/X button per term
      const buttons = screen.getAllByRole('button');
      // At least as many buttons as terms (add button + per-chip X buttons)
      expect(buttons.length).toBeGreaterThanOrEqual(SAMPLE_TERMS.length);
    });
  });

  // --- TYPE_COLORS chip colours ---

  it('name-type chip has bg-blue-900 class', async () => {
    await renderPersonalDictionary();
    await waitFor(() => {
      const karthikText = screen.getByText('Karthik');
      const chip = karthikText.closest('span') ?? karthikText.parentElement;
      expect(chip?.className).toMatch(/bg-blue-900/);
    });
  });

  it('music_term-type chip has bg-purple-900 class', async () => {
    await renderPersonalDictionary();
    await waitFor(() => {
      const text = screen.getByText('arpeggio');
      const chip = text.closest('span') ?? text.parentElement;
      expect(chip?.className).toMatch(/bg-purple-900/);
    });
  });

  it('technical-type chip has bg-green-900 class', async () => {
    await renderPersonalDictionary();
    await waitFor(() => {
      const text = screen.getByText('pgvector');
      const chip = text.closest('span') ?? text.parentElement;
      expect(chip?.className).toMatch(/bg-green-900/);
    });
  });

  it('place-type chip has bg-amber-900 class', async () => {
    await renderPersonalDictionary();
    await waitFor(() => {
      const text = screen.getByText('Seattle');
      const chip = text.closest('span') ?? text.parentElement;
      expect(chip?.className).toMatch(/bg-amber-900/);
    });
  });

  it('acronym-type chip has bg-rose-900 class', async () => {
    await renderPersonalDictionary();
    await waitFor(() => {
      const text = screen.getByText('CODE');
      const chip = text.closest('span') ?? text.parentElement;
      expect(chip?.className).toMatch(/bg-rose-900/);
    });
  });

  it('general-type chip has bg-slate-700 class', async () => {
    await renderPersonalDictionary();
    await waitFor(() => {
      const text = screen.getByText('meeting');
      const chip = text.closest('span') ?? text.parentElement;
      expect(chip?.className).toMatch(/bg-slate-700/);
    });
  });

  // --- Add term interaction ---

  it('typing in the input and clicking Add calls addTerm', async () => {
    mockListTerms
      .mockResolvedValueOnce(SAMPLE_TERMS)
      .mockResolvedValue([
        ...SAMPLE_TERMS,
        { id: 'new-id', term: 'new-jargon', term_type: 'general', usage_count: 0 },
      ]);

    await renderPersonalDictionary();
    await waitFor(() => expect(mockListTerms).toHaveBeenCalled());

    const input = document.querySelector<HTMLInputElement>('input:not([type="hidden"])');
    expect(input).toBeTruthy();

    fireEvent.change(input!, { target: { value: 'new-jargon' } });

    // Click the add button (first button or aria-label contains "add" / has Plus icon)
    const addButton = screen.getAllByRole('button').find(
      (b) =>
        b.getAttribute('aria-label')?.toLowerCase().includes('add') ||
        (b.querySelector('svg') !== null && b.closest('div')?.querySelector('input') !== null),
    ) ?? screen.getAllByRole('button')[0];

    fireEvent.click(addButton);

    await waitFor(() => {
      expect(mockAddTerm).toHaveBeenCalledWith(
        expect.objectContaining({ term: 'new-jargon' }),
      );
    });
  });

  it('pressing Enter in the input calls addTerm', async () => {
    mockListTerms.mockResolvedValue(SAMPLE_TERMS);
    mockAddTerm.mockResolvedValue({
      id: 'enter-id',
      term: 'enter-term',
      term_type: 'general',
      usage_count: 0,
    });

    await renderPersonalDictionary();
    await waitFor(() => expect(mockListTerms).toHaveBeenCalled());

    const input = document.querySelector<HTMLInputElement>('input:not([type="hidden"])');
    fireEvent.change(input!, { target: { value: 'enter-term' } });
    fireEvent.keyDown(input!, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(mockAddTerm).toHaveBeenCalledWith(
        expect.objectContaining({ term: 'enter-term' }),
      );
    });
  });

  // --- Delete term interaction ---

  it('clicking X button on a chip calls deleteTerm with that term id', async () => {
    await renderPersonalDictionary();
    await waitFor(() => screen.getByText('Karthik'));

    // Find the X button near the 'Karthik' chip
    const karthikText = screen.getByText('Karthik');
    const chip = karthikText.closest('span') ?? karthikText.parentElement;
    const xButton = chip?.querySelector('button') ?? within(chip as HTMLElement).getByRole('button');

    fireEvent.click(xButton!);

    await waitFor(() => {
      expect(mockDeleteTerm).toHaveBeenCalledWith('id-1');
    });
  });

  // --- Error display ---

  it('displays a limit-reached message when addTerm rejects with 400 status', async () => {
    const limitError = Object.assign(new Error('Dictionary limit of 2000 reached'), {
      status: 400,
      code: 'limit_exceeded',
      detail: 'Dictionary limit of 2000 reached',
    });
    mockAddTerm.mockRejectedValue(limitError);
    mockListTerms.mockResolvedValue([]);

    await renderPersonalDictionary();
    await waitFor(() => expect(mockListTerms).toHaveBeenCalled());

    const input = document.querySelector<HTMLInputElement>('input:not([type="hidden"])');
    fireEvent.change(input!, { target: { value: 'overflow-term' } });
    fireEvent.keyDown(input!, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      const bodyText = document.body.textContent?.toLowerCase() ?? '';
      const hasLimitMessage =
        bodyText.includes('limit') ||
        bodyText.includes('2000') ||
        bodyText.includes('maximum') ||
        bodyText.includes('full');
      expect(hasLimitMessage).toBe(true);
    });
  });

  it('displays a duplicate-term message when addTerm rejects with 409 status', async () => {
    const dupError = Object.assign(new Error('Term already exists'), {
      status: 409,
      code: 'duplicate_term',
      detail: 'Term already exists',
    });
    mockAddTerm.mockRejectedValue(dupError);
    mockListTerms.mockResolvedValue([]);

    await renderPersonalDictionary();
    await waitFor(() => expect(mockListTerms).toHaveBeenCalled());

    const input = document.querySelector<HTMLInputElement>('input:not([type="hidden"])');
    fireEvent.change(input!, { target: { value: 'dup-term' } });
    fireEvent.keyDown(input!, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      const bodyText = document.body.textContent?.toLowerCase() ?? '';
      const hasDupMessage =
        bodyText.includes('duplicate') ||
        bodyText.includes('already') ||
        bodyText.includes('exists');
      expect(hasDupMessage).toBe(true);
    });
  });

  // --- listTerms called on mount ---

  it('calls listTerms on mount to populate chips', async () => {
    await renderPersonalDictionary();
    await waitFor(() => {
      expect(mockListTerms).toHaveBeenCalledTimes(1);
    });
  });

  // --- listTerms called after add/delete to refresh ---

  it('refreshes the term list after a successful add', async () => {
    mockListTerms
      .mockResolvedValueOnce(SAMPLE_TERMS)        // initial load
      .mockResolvedValue([...SAMPLE_TERMS]);       // refresh after add

    await renderPersonalDictionary();
    await waitFor(() => expect(mockListTerms).toHaveBeenCalledTimes(1));

    const input = document.querySelector<HTMLInputElement>('input:not([type="hidden"])');
    fireEvent.change(input!, { target: { value: 'fresh-term' } });
    fireEvent.keyDown(input!, { key: 'Enter', code: 'Enter' });

    await waitFor(() => {
      expect(mockListTerms).toHaveBeenCalledTimes(2);
    });
  });
});

// ---------------------------------------------------------------------------
// dictionary API client module
// ---------------------------------------------------------------------------

describe('dictionary API client (task 4.1)', () => {
  it('dictionary API module is importable', async () => {
    const mod = await import('../api/dictionary');
    expect(mod).toBeDefined();
  });

  it('exports listTerms function', async () => {
    const mod = await import('../api/dictionary');
    expect(typeof mod.listTerms).toBe('function');
  });

  it('exports addTerm function', async () => {
    const mod = await import('../api/dictionary');
    expect(typeof mod.addTerm).toBe('function');
  });

  it('exports updateTerm function', async () => {
    const mod = await import('../api/dictionary');
    expect(typeof mod.updateTerm).toBe('function');
  });

  it('exports deleteTerm function', async () => {
    const mod = await import('../api/dictionary');
    expect(typeof mod.deleteTerm).toBe('function');
  });

  it('exports bulkImport function', async () => {
    const mod = await import('../api/dictionary');
    expect(typeof mod.bulkImport).toBe('function');
  });

  it('exports exportTerms function', async () => {
    const mod = await import('../api/dictionary');
    expect(typeof mod.exportTerms).toBe('function');
  });
});
