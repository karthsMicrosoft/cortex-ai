/**
 * Task 2.1 / 2.2 — NoteCard + ProcessingBadge — TDD red
 *
 * Tests that `frontend/src/components/NoteCard.tsx`:
 *   - Renders content snippet, category chip, date
 *   - Renders a processing-status badge (per critique mitigation #5)
 *     covering all five states: raw | transcribed | processed | enriched | failed
 *   - Shows an "AI-suggested" badge on AI-populated values (per B8)
 *   - Clicking the card invokes onPress / navigation
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const baseNote = {
  localId: 'note-123',
  serverId: 'server-uuid-1',
  content: 'This is the note content for testing purposes.',
  sourceType: 'voice' as const,
  category: 'Music' as const,
  tags: ['jazz', 'guitar'],
  syncStatus: 'synced' as const,
  processingStatus: 'enriched' as const,
  createdAt: new Date('2026-04-01T10:00:00Z'),
  updatedAt: new Date('2026-04-01T10:01:00Z'),
};

// ---------------------------------------------------------------------------
// Import component under test
// ---------------------------------------------------------------------------

import { NoteCard } from '../components/NoteCard';

function renderCard(props: Partial<Parameters<typeof NoteCard>[0]> = {}) {
  return render(
    <MemoryRouter>
      <NoteCard note={{ ...baseNote, ...props.note }} onPress={props.onPress} />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('NoteCard (Task 2.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --- Content snippet ---

  it('renders a content snippet', () => {
    renderCard();
    expect(screen.getByText(/This is the note content/i)).toBeInTheDocument();
  });

  // --- Category chip ---

  it('renders a category chip', () => {
    renderCard();
    expect(screen.getByText(/Music/i)).toBeInTheDocument();
  });

  it('shows the correct category for a non-Music note', () => {
    renderCard({ note: { ...baseNote, category: 'Ideas' as const } });
    expect(screen.getByText(/Ideas/i)).toBeInTheDocument();
  });

  // --- Date ---

  it('renders a date or relative time', () => {
    renderCard();
    // Date should appear somewhere in the card — may be relative ("29 days ago") or absolute
    const card = screen.getByRole('article');
    // Should have SOME time/date reference
    expect(card.textContent).toMatch(/ago|day|hour|min|2026|Apr|01|just now/i);
  });

  // --- Processing badge (mitigation #5) ---

  it('renders a processing badge element', () => {
    renderCard();
    // Badge should exist — typically role="status" or a data-testid
    const badge = screen.getByRole('status');
    expect(badge).toBeInTheDocument();
  });

  it('shows "enriched" processing status', () => {
    renderCard({ note: { ...baseNote, processingStatus: 'enriched' as const } });
    expect(screen.getByRole('status').textContent).toMatch(/enriched/i);
  });

  it('shows "raw" processing status', () => {
    renderCard({ note: { ...baseNote, processingStatus: 'raw' as const } });
    expect(screen.getByRole('status').textContent).toMatch(/raw/i);
  });

  it('shows "transcribed" processing status', () => {
    renderCard({ note: { ...baseNote, processingStatus: 'transcribed' as const } });
    expect(screen.getByRole('status').textContent).toMatch(/transcribed/i);
  });

  it('shows "processed" processing status', () => {
    renderCard({ note: { ...baseNote, processingStatus: 'processed' as const } });
    expect(screen.getByRole('status').textContent).toMatch(/processed/i);
  });

  it('shows "failed" processing status with distinct styling', () => {
    renderCard({ note: { ...baseNote, processingStatus: 'failed' as const } });
    const badge = screen.getByRole('status');
    expect(badge.textContent).toMatch(/failed/i);
    // Failed should have a red or error color class
    expect(badge.className).toMatch(/red|error|danger/i);
  });

  // --- AI-suggested badge (B8) ---

  it('shows AI-suggested badge on category when aiSuggestedFields includes category', () => {
    renderCard({ note: { ...baseNote, aiSuggestedFields: ['category'] } });
    const badges = screen.getAllByText(/ai.suggested|ai suggested/i);
    expect(badges.length).toBeGreaterThan(0);
  });

  it('does NOT show AI-suggested badge when aiSuggestedFields is empty', () => {
    renderCard({ note: { ...baseNote, aiSuggestedFields: [] } });
    const badges = screen.queryAllByText(/ai.suggested|ai suggested/i);
    expect(badges.length).toBe(0);
  });

  // --- Tags ---

  it('renders tags', () => {
    renderCard();
    expect(screen.getByText('jazz')).toBeInTheDocument();
    expect(screen.getByText('guitar')).toBeInTheDocument();
  });

  // --- Click / tap ---

  it('calls onPress when the card is clicked', () => {
    const onPress = vi.fn();
    renderCard({ onPress });
    fireEvent.click(screen.getByRole('article'));
    expect(onPress).toHaveBeenCalledWith(baseNote.localId);
  });

  it('renders as a clickable element', () => {
    renderCard();
    const card = screen.getByRole('article');
    expect(card).toBeInTheDocument();
    // Should be clickable (button or have onClick)
    expect(card.tagName === 'BUTTON' || card.getAttribute('role') === 'button' || card.onclick !== null || card.className.includes('cursor')).toBeTruthy();
  });

  // --- Sync status ---

  it('renders a pending sync indicator when syncStatus=pending', () => {
    renderCard({ note: { ...baseNote, syncStatus: 'pending' as const } });
    // Some indicator should show pending/offline state
    expect(document.body.textContent).toMatch(/pending|sync|offline/i);
  });
});
