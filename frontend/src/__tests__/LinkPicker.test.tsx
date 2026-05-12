/**
 * LinkPicker.test.tsx — PR 6.3 (Manual link picker modal)
 *
 * Coverage:
 *   - Debounced search calls listNotes with the trimmed query.
 *   - Search results are rendered; the current note is filtered out.
 *   - Clicking a result enters confirm step; confirm POSTs createManualLink
 *     and triggers onCreated + onClose.
 *   - Errors from createManualLink surface inline and the modal stays open.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

const { mockListNotes, mockCreateManualLink } = vi.hoisted(() => ({
  mockListNotes: vi.fn(),
  mockCreateManualLink: vi.fn(),
}));

vi.mock('../api/notes', () => ({
  listNotes: mockListNotes,
}));

vi.mock('../api/links', () => ({
  createManualLink: mockCreateManualLink,
}));

import { LinkPicker } from '../components/LinkPicker';

beforeEach(() => {
  vi.clearAllMocks();
});

const SAMPLE_RESULTS = [
  {
    id: 'tgt-1',
    user_id: 'u1',
    content: 'A wonderful target note about plants',
    title: 'Plants',
    source_type: 'text',
    category: 'Ideas',
    entities: [],
    music_metadata: {},
    processing_status: 'enriched',
    sync_status: 'synced',
    tags: [],
    created_at: '2026-05-10T00:00:00Z',
    updated_at: '2026-05-10T00:00:00Z',
  },
  {
    id: 'src-1', // same as sourceNoteId — must be filtered out
    user_id: 'u1',
    content: 'me',
    title: 'Me',
    source_type: 'text',
    category: 'Ideas',
    entities: [],
    music_metadata: {},
    processing_status: 'enriched',
    sync_status: 'synced',
    tags: [],
    created_at: '2026-05-10T00:00:00Z',
    updated_at: '2026-05-10T00:00:00Z',
  },
];

describe('LinkPicker (PR 6.3)', () => {
  it('debounces search and calls listNotes with the trimmed query', async () => {
    mockListNotes.mockResolvedValue({ items: SAMPLE_RESULTS, total: 2 });
    render(
      <LinkPicker
        sourceNoteId="src-1"
        onClose={vi.fn()}
        onCreated={vi.fn()}
      />,
    );
    const input = screen.getByLabelText(/search notes/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'plant' } });
    expect(mockListNotes).not.toHaveBeenCalled();
    await waitFor(
      () => expect(mockListNotes).toHaveBeenCalledTimes(1),
      { timeout: 1500 },
    );
    expect(mockListNotes).toHaveBeenCalledWith({ q: 'plant', limit: 20 });
  });

  it('filters out the current note from results', async () => {
    mockListNotes.mockResolvedValue({ items: SAMPLE_RESULTS, total: 2 });
    render(
      <LinkPicker
        sourceNoteId="src-1"
        onClose={vi.fn()}
        onCreated={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText(/search notes/i), {
      target: { value: 'note' },
    });
    await waitFor(
      () => expect(screen.getByText(/plants/i)).toBeInTheDocument(),
      { timeout: 1500 },
    );
    expect(screen.queryByText(/^Me$/)).not.toBeInTheDocument();
  });

  it('clicking a result then confirm calls createManualLink and onCreated', async () => {
    mockListNotes.mockResolvedValue({ items: SAMPLE_RESULTS, total: 2 });
    mockCreateManualLink.mockResolvedValue({
      id: 'lnk',
      source_note_id: 'src-1',
      target_note_id: 'tgt-1',
      link_type: 'manual',
      score: null,
      created_at: '2026-05-10T00:00:00Z',
    });
    const onCreated = vi.fn();
    const onClose = vi.fn();
    render(
      <LinkPicker
        sourceNoteId="src-1"
        onClose={onClose}
        onCreated={onCreated}
      />,
    );
    fireEvent.change(screen.getByLabelText(/search notes/i), {
      target: { value: 'plant' },
    });
    const card = await screen.findByText(/plants/i, undefined, { timeout: 1500 });
    fireEvent.click(card);
    const confirmBtn = await screen.findByRole('button', { name: /confirm link/i });
    fireEvent.click(confirmBtn);
    await waitFor(() => {
      expect(mockCreateManualLink).toHaveBeenCalledWith('src-1', 'tgt-1');
    });
    await waitFor(() => {
      expect(onCreated).toHaveBeenCalledTimes(1);
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  it('surfaces inline error when createManualLink fails and keeps modal open', async () => {
    mockListNotes.mockResolvedValue({ items: SAMPLE_RESULTS, total: 2 });
    mockCreateManualLink.mockRejectedValue(new Error('Server exploded'));
    const onCreated = vi.fn();
    const onClose = vi.fn();
    render(
      <LinkPicker
        sourceNoteId="src-1"
        onClose={onClose}
        onCreated={onCreated}
      />,
    );
    fireEvent.change(screen.getByLabelText(/search notes/i), {
      target: { value: 'plant' },
    });
    const card = await screen.findByText(/plants/i, undefined, { timeout: 1500 });
    fireEvent.click(card);
    fireEvent.click(await screen.findByRole('button', { name: /confirm link/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/server exploded/i);
    expect(onCreated).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });
});
