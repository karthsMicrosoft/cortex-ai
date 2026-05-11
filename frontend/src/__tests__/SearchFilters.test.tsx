/**
 * Phase 4 / Round 16 / PR 4.3 — SearchFilters TDD red
 *
 * Tests for the new <SearchFilters /> sidebar component:
 *   - Renders all 6 categories + "All" option
 *   - Category change calls onChange with new value
 *   - Tag chip click toggles selection
 *   - Date inputs update onChange
 *   - "Clear filters" button hidden when no filters set
 *   - "Clear filters" click resets all
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SearchFilters } from '../components/SearchFilters';
import type { SearchFiltersValue } from '../components/SearchFilters';

const ALL_CATEGORIES = [
  'Music',
  'Fitness',
  'Journal',
  'Ideas',
  'Spiritual',
  'Learning',
] as const;

function setup(
  value: SearchFiltersValue = {},
  availableTags: string[] = ['mentorship', 'book', 'workout'],
) {
  const onChange = vi.fn();
  render(
    <SearchFilters value={value} onChange={onChange} availableTags={availableTags} />,
  );
  return { onChange };
}

describe('SearchFilters (P4 / R16 / PR 4.3)', () => {
  // --- Category ---

  it('renders all 6 categories plus an "All" option', () => {
    setup();
    const select = screen.getByLabelText(/category/i) as HTMLSelectElement;
    const optionTexts = Array.from(select.options).map((o) => o.textContent ?? '');
    expect(optionTexts).toContain('All');
    for (const cat of ALL_CATEGORIES) {
      expect(optionTexts).toContain(cat);
    }
    // 6 categories + "All"
    expect(select.options.length).toBe(7);
  });

  it('category change calls onChange with new value', () => {
    const { onChange } = setup();
    const select = screen.getByLabelText(/category/i) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'Music' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ category: 'Music' }),
    );
  });

  it('selecting "All" clears the category from value', () => {
    const { onChange } = setup({ category: 'Music' });
    const select = screen.getByLabelText(/category/i) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: '' } });
    const last = onChange.mock.calls.at(-1)![0] as SearchFiltersValue;
    expect(last.category).toBeUndefined();
  });

  // --- Tags ---

  it('renders a chip for each available tag', () => {
    setup({}, ['alpha', 'beta', 'gamma']);
    expect(screen.getByRole('button', { name: /^alpha$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^beta$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^gamma$/i })).toBeInTheDocument();
  });

  it('clicking an unselected tag chip adds it to value via onChange', () => {
    const { onChange } = setup({ tags: [] }, ['mentorship', 'book']);
    fireEvent.click(screen.getByRole('button', { name: /^mentorship$/i }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ tags: ['mentorship'] }),
    );
  });

  it('clicking a selected tag chip removes it (toggles off)', () => {
    const { onChange } = setup({ tags: ['mentorship', 'book'] }, ['mentorship', 'book']);
    fireEvent.click(screen.getByRole('button', { name: /^mentorship$/i }));
    const last = onChange.mock.calls.at(-1)![0] as SearchFiltersValue;
    expect(last.tags).toEqual(['book']);
  });

  it('selected tag chips have aria-pressed="true"', () => {
    setup({ tags: ['book'] }, ['mentorship', 'book']);
    const book = screen.getByRole('button', { name: /^book$/i });
    expect(book).toHaveAttribute('aria-pressed', 'true');
    const mentorship = screen.getByRole('button', { name: /^mentorship$/i });
    expect(mentorship).toHaveAttribute('aria-pressed', 'false');
  });

  // --- Date range ---

  it('"Since" date input updates onChange', () => {
    const { onChange } = setup();
    const since = screen.getByLabelText(/since/i) as HTMLInputElement;
    fireEvent.change(since, { target: { value: '2026-04-01' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ since: '2026-04-01' }),
    );
  });

  it('"Until" date input updates onChange', () => {
    const { onChange } = setup();
    const until = screen.getByLabelText(/until/i) as HTMLInputElement;
    fireEvent.change(until, { target: { value: '2026-05-15' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ until: '2026-05-15' }),
    );
  });

  it('clearing a date input removes it from value', () => {
    const { onChange } = setup({ since: '2026-04-01' });
    const since = screen.getByLabelText(/since/i) as HTMLInputElement;
    fireEvent.change(since, { target: { value: '' } });
    const last = onChange.mock.calls.at(-1)![0] as SearchFiltersValue;
    expect(last.since).toBeUndefined();
  });

  // --- Clear filters ---

  it('"Clear filters" button is hidden when no filters are set', () => {
    setup({});
    expect(screen.queryByRole('button', { name: /clear filters/i })).not.toBeInTheDocument();
  });

  it('"Clear filters" button is visible when any filter is set', () => {
    setup({ category: 'Music' });
    expect(screen.getByRole('button', { name: /clear filters/i })).toBeInTheDocument();
  });

  it('"Clear filters" click resets all filters via onChange({})', () => {
    const { onChange } = setup({
      category: 'Music',
      tags: ['mentorship'],
      since: '2026-04-01',
      until: '2026-05-15',
    });
    fireEvent.click(screen.getByRole('button', { name: /clear filters/i }));
    expect(onChange).toHaveBeenCalledWith({});
  });
});
