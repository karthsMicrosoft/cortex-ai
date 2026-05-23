/**
 * CanvasListPage.test.tsx — Phase 7 PR B
 *
 * Tests the canvas list page: fetches canvases, renders grid of cards,
 * create + delete + navigate actions, loading/empty/error states.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mock canvas API
// ---------------------------------------------------------------------------

vi.mock('../api/canvas', () => ({
  listCanvases: vi.fn(),
  createCanvas: vi.fn(),
  deleteCanvas: vi.fn(),
  getCanvas: vi.fn(),
  updateCanvas: vi.fn(),
  addCanvasItem: vi.fn(),
  updateCanvasItem: vi.fn(),
  batchUpdateItems: vi.fn(),
  deleteCanvasItem: vi.fn(),
  addCanvasEdge: vi.fn(),
  deleteCanvasEdge: vi.fn(),
  autoLayoutCanvas: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Mock useNavigate
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

// ---------------------------------------------------------------------------
// Mock auth store (so AuthGate would pass; we don't actually use it here)
// ---------------------------------------------------------------------------

const { mockUseAuthStore } = vi.hoisted(() => {
  const state = { accessToken: 'test-token', user: { id: 'u1' }, isRestoring: false };
  const mockUseAuthStore = Object.assign(
    (selector: (s: typeof state) => unknown) => selector(state),
    { getState: () => state, subscribe: () => () => {}, setState: () => {} },
  );
  return { mockUseAuthStore };
});
vi.mock('../store/authStore', () => ({ useAuthStore: mockUseAuthStore }));

// ---------------------------------------------------------------------------
// Reset canvasStore between tests
// ---------------------------------------------------------------------------

import { useCanvasStore } from '../store/canvasStore';
import * as canvasApi from '../api/canvas';
import CanvasListPage from '../pages/CanvasListPage';

const CANVAS_FIXTURES = [
  {
    id: 'c1',
    title: 'Roadmap brainstorm',
    description: 'Ideas for Q3',
    viewport_x: 0,
    viewport_y: 0,
    viewport_zoom: 1,
    item_count: 5,
    created_at: '2026-04-10T09:00:00Z',
    updated_at: '2026-04-12T12:00:00Z',
  },
  {
    id: 'c2',
    title: 'Story plot',
    description: null,
    viewport_x: 0,
    viewport_y: 0,
    viewport_zoom: 1,
    item_count: 0,
    created_at: '2026-04-11T07:00:00Z',
    updated_at: '2026-04-11T07:00:00Z',
  },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <CanvasListPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useCanvasStore.setState({ canvases: [], isLoading: false, error: null });
  (canvasApi.listCanvases as ReturnType<typeof vi.fn>).mockResolvedValue({
    items: CANVAS_FIXTURES,
    total: CANVAS_FIXTURES.length,
  });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('CanvasListPage', () => {
  it('renders the Canvases heading', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /canvases/i })).toBeInTheDocument();
    });
  });

  it('renders a New Canvas button', async () => {
    renderPage();
    expect(screen.getByTestId('canvas-new-button')).toBeInTheDocument();
  });

  it('fetches and displays the canvas list', async () => {
    renderPage();
    await waitFor(() => {
      expect(canvasApi.listCanvases).toHaveBeenCalled();
      expect(screen.getByTestId('canvas-card-c1')).toBeInTheDocument();
      expect(screen.getByTestId('canvas-card-c2')).toBeInTheDocument();
    });
  });

  it('shows empty state when no canvases', async () => {
    (canvasApi.listCanvases as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [], total: 0 });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/no canvases yet/i)).toBeInTheDocument();
    });
  });

  it('shows loading state initially', () => {
    (canvasApi.listCanvases as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByRole('status', { name: /loading canvases/i })).toBeInTheDocument();
  });

  it('shows error state on fetch failure', async () => {
    (canvasApi.listCanvases as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('boom'));
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/boom/);
    });
  });

  it('creates a new canvas on button click and navigates to editor', async () => {
    (canvasApi.createCanvas as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: 'new-id',
      title: 'Untitled canvas',
      description: null,
      viewport_x: 0,
      viewport_y: 0,
      viewport_zoom: 1,
      item_count: 0,
      created_at: '2026-05-01T00:00:00Z',
      updated_at: '2026-05-01T00:00:00Z',
    });
    renderPage();
    await waitFor(() => expect(canvasApi.listCanvases).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId('canvas-new-button'));
    await waitFor(() => {
      expect(canvasApi.createCanvas).toHaveBeenCalled();
      expect(mockNavigate).toHaveBeenCalledWith('/canvas/new-id');
    });
  });

  it('navigates to editor on card click', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('canvas-card-c1')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('canvas-card-c1'));
    expect(mockNavigate).toHaveBeenCalledWith('/canvas/c1');
  });

  it('deletes a canvas on delete button click', async () => {
    (canvasApi.deleteCanvas as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    renderPage();
    await waitFor(() => expect(screen.getByTestId('canvas-delete-c1')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('canvas-delete-c1'));
    await waitFor(() => {
      expect(canvasApi.deleteCanvas).toHaveBeenCalledWith('c1');
    });
  });

  it('shows item count on cards', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('canvas-item-count-c1')).toHaveTextContent(/5/);
      expect(screen.getByTestId('canvas-item-count-c2')).toHaveTextContent(/0/);
    });
  });

  it('shows relative updated time on cards', async () => {
    renderPage();
    await waitFor(() => {
      const el = screen.getByTestId('canvas-updated-c1');
      expect(el.textContent).toMatch(/ago|years|months|days/i);
    });
  });

  it('renders description text when present', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Ideas for Q3')).toBeInTheDocument();
    });
  });

  it('renders the Layout icon in the header', async () => {
    renderPage();
    const heading = await screen.findByRole('heading', { name: /canvases/i });
    expect(heading.querySelector('svg')).not.toBeNull();
  });
});
