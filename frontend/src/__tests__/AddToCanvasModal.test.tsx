/**
 * AddToCanvasModal.test.tsx — PR C tests for the canvas picker modal.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../api/canvas', () => ({
  listCanvases: vi.fn(),
  createCanvas: vi.fn(),
  addCanvasItem: vi.fn(),
}));

import { AddToCanvasModal } from '../components/AddToCanvasModal';
import * as canvasApi from '../api/canvas';
import { ApiError } from '../api/client';

const mockedListCanvases = vi.mocked(canvasApi.listCanvases);
const mockedCreateCanvas = vi.mocked(canvasApi.createCanvas);
const mockedAddCanvasItem = vi.mocked(canvasApi.addCanvasItem);

function makeCanvas(id: string, title: string, items = 0): canvasApi.CanvasOut {
  return {
    id,
    title,
    description: null,
    viewport_x: 0,
    viewport_y: 0,
    viewport_zoom: 1,
    item_count: items,
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
  };
}

function makeItem(id: string): canvasApi.CanvasItemOut {
  return {
    id,
    canvas_id: 'c1',
    note_id: 'note-1',
    item_type: 'note',
    position_x: 100,
    position_y: 100,
    width: null,
    height: null,
    color: null,
    label: null,
    z_index: 0,
    version: 1,
    last_known_title: null,
    note_title: null,
    note_summary: null,
    note_content: null,
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
  };
}

function renderModal(props: Partial<React.ComponentProps<typeof AddToCanvasModal>> = {}) {
  const onClose = vi.fn();
  const onAdded = vi.fn();
  const utils = render(
    <MemoryRouter>
      <AddToCanvasModal
        noteId="note-1"
        noteTitle="My Note"
        isOpen={true}
        onClose={onClose}
        onAdded={onAdded}
        {...props}
      />
    </MemoryRouter>,
  );
  return { ...utils, onClose, onAdded };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedListCanvases.mockResolvedValue({ items: [], total: 0 });
});

describe('AddToCanvasModal (PR C)', () => {
  it('renders the modal when isOpen=true', async () => {
    mockedListCanvases.mockResolvedValueOnce({
      items: [makeCanvas('c1', 'Canvas One')],
      total: 1,
    });
    renderModal();
    expect(await screen.findByRole('dialog', { name: /add to canvas/i })).toBeInTheDocument();
  });

  it('does not render when isOpen=false', () => {
    renderModal({ isOpen: false });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('fetches and displays the canvas list', async () => {
    mockedListCanvases.mockResolvedValueOnce({
      items: [makeCanvas('c1', 'Alpha', 3), makeCanvas('c2', 'Beta', 5)],
      total: 2,
    });
    renderModal();
    expect(await screen.findByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();
    expect(screen.getByText(/3 items/)).toBeInTheDocument();
  });

  it('shows the loading state while fetching', async () => {
    let resolveFn: ((v: { items: canvasApi.CanvasOut[]; total: number }) => void) | undefined;
    mockedListCanvases.mockImplementationOnce(
      () =>
        new Promise((res) => {
          resolveFn = res;
        }),
    );
    renderModal();
    expect(screen.getByTestId('add-to-canvas-loading')).toBeInTheDocument();
    resolveFn?.({ items: [], total: 0 });
    await waitFor(() => {
      expect(screen.queryByTestId('add-to-canvas-loading')).not.toBeInTheDocument();
    });
  });

  it('shows the empty state when no canvases exist', async () => {
    mockedListCanvases.mockResolvedValueOnce({ items: [], total: 0 });
    renderModal();
    expect(await screen.findByTestId('add-to-canvas-empty')).toBeInTheDocument();
  });

  it('adds note to the selected canvas', async () => {
    mockedListCanvases.mockResolvedValueOnce({
      items: [makeCanvas('c1', 'Alpha')],
      total: 1,
    });
    mockedAddCanvasItem.mockResolvedValueOnce(makeItem('i1'));
    renderModal();
    const row = await screen.findByTestId('canvas-row-c1');
    fireEvent.click(row);
    await waitFor(() => {
      expect(mockedAddCanvasItem).toHaveBeenCalledWith('c1', {
        note_id: 'note-1',
        item_type: 'note',
        position_x: 100,
        position_y: 100,
      });
    });
  });

  it('shows a success banner after adding', async () => {
    mockedListCanvases.mockResolvedValueOnce({
      items: [makeCanvas('c1', 'Alpha')],
      total: 1,
    });
    mockedAddCanvasItem.mockResolvedValueOnce(makeItem('i1'));
    renderModal();
    fireEvent.click(await screen.findByTestId('canvas-row-c1'));
    expect(await screen.findByTestId('add-to-canvas-success')).toHaveTextContent(/Alpha/);
  });

  it('shows an error when note is already on the canvas', async () => {
    mockedListCanvases.mockResolvedValueOnce({
      items: [makeCanvas('c1', 'Alpha')],
      total: 1,
    });
    mockedAddCanvasItem.mockRejectedValueOnce(
      new ApiError(409, 'duplicate', 'Note is already on this canvas'),
    );
    renderModal();
    fireEvent.click(await screen.findByTestId('canvas-row-c1'));
    const err = await screen.findByTestId('add-to-canvas-error');
    expect(err).toHaveTextContent(/already on this canvas/i);
  });

  it('creates a new canvas and adds the note', async () => {
    mockedListCanvases.mockResolvedValueOnce({ items: [], total: 0 });
    mockedCreateCanvas.mockResolvedValueOnce(makeCanvas('new-1', 'Brand new'));
    mockedAddCanvasItem.mockResolvedValueOnce(makeItem('i1'));
    renderModal();
    await screen.findByTestId('add-to-canvas-empty');
    fireEvent.click(screen.getByTestId('add-to-canvas-create-new'));
    await waitFor(() => {
      expect(mockedCreateCanvas).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(mockedAddCanvasItem).toHaveBeenCalledWith('new-1', expect.objectContaining({
        note_id: 'note-1',
        item_type: 'note',
      }));
    });
  });

  it('calls onClose on backdrop click', async () => {
    mockedListCanvases.mockResolvedValueOnce({ items: [], total: 0 });
    const { onClose } = renderModal();
    const backdrop = await screen.findByTestId('add-to-canvas-modal');
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not call onClose when clicking inside the modal card', async () => {
    mockedListCanvases.mockResolvedValueOnce({ items: [], total: 0 });
    const { onClose } = renderModal();
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(dialog);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('calls onAdded callback on success', async () => {
    mockedListCanvases.mockResolvedValueOnce({
      items: [makeCanvas('c1', 'Alpha')],
      total: 1,
    });
    mockedAddCanvasItem.mockResolvedValueOnce(makeItem('i1'));
    const { onAdded } = renderModal();
    fireEvent.click(await screen.findByTestId('canvas-row-c1'));
    await waitFor(() => {
      expect(onAdded).toHaveBeenCalledWith('c1');
    });
  });
});
