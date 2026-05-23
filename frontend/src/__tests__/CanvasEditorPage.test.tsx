/**
 * CanvasEditorPage.test.tsx — Phase 7 PR B
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mock @xyflow/react — heavy canvas library cannot run in jsdom.
// The mock renders nodes by looking up custom components in `nodeTypes`,
// so tests can assert on NoteCardNode / GroupNode / TextNode rendering.
// ---------------------------------------------------------------------------

vi.mock('@xyflow/react', () => {
  const React = require('react') as typeof import('react');
  const Handle = (props: Record<string, unknown>) =>
    React.createElement('div', { 'data-testid': 'rf-handle', ...props });
  const ReactFlow = (props: {
    nodes: { id: string; type?: string; data: Record<string, unknown> }[];
    edges: { id: string }[];
    nodeTypes?: Record<string, React.ComponentType<{ id: string; data: unknown }>>;
    children?: React.ReactNode;
  }) => {
    const { nodes = [], edges = [], nodeTypes = {}, children } = props;
    return React.createElement(
      'div',
      {
        'data-testid': 'reactflow',
        'data-node-count': String(nodes.length),
        'data-edge-count': String(edges.length),
      },
      nodes.map((n) => {
        const Comp = n.type ? nodeTypes[n.type] : undefined;
        return Comp
          ? React.createElement(Comp, { key: n.id, id: n.id, data: n.data })
          : React.createElement('div', { key: n.id, 'data-testid': `unknown-node-${n.id}` });
      }),
      children,
    );
  };
  return {
    ReactFlow,
    Background: () => React.createElement('div', { 'data-testid': 'rf-background' }),
    Controls: () => React.createElement('div', { 'data-testid': 'rf-controls' }),
    MiniMap: () => React.createElement('div', { 'data-testid': 'rf-minimap' }),
    Panel: ({ children }: { children?: React.ReactNode }) =>
      React.createElement('div', { 'data-testid': 'rf-panel' }, children),
    Handle,
    Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
    ReactFlowProvider: ({ children }: { children?: React.ReactNode }) =>
      React.createElement('div', null, children),
    useNodesState: (initial: unknown[]) => {
      const [nodes, setNodes] = React.useState(initial ?? []);
      const onChange = React.useCallback(() => {}, []);
      return [nodes, setNodes, onChange];
    },
    useEdgesState: (initial: unknown[]) => {
      const [edges, setEdges] = React.useState(initial ?? []);
      const onChange = React.useCallback(() => {}, []);
      return [edges, setEdges, onChange];
    },
    useReactFlow: () => ({
      getViewport: () => ({ x: 0, y: 0, zoom: 1 }),
      setViewport: vi.fn(),
      fitView: vi.fn(),
      project: (p: unknown) => p,
      screenToFlowPosition: (p: unknown) => p,
    }),
    addEdge: (edge: unknown, edges: unknown[]) => [...edges, edge],
  };
});

// ---------------------------------------------------------------------------
// Mock CSS import
// ---------------------------------------------------------------------------

vi.mock('@xyflow/react/dist/style.css', () => ({}));

// ---------------------------------------------------------------------------
// Mock canvas API
// ---------------------------------------------------------------------------

vi.mock('../api/canvas', () => ({
  listCanvases: vi.fn(),
  createCanvas: vi.fn(),
  getCanvas: vi.fn(),
  updateCanvas: vi.fn(),
  deleteCanvas: vi.fn(),
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

import * as canvasApi from '../api/canvas';
import CanvasEditorPage from '../pages/CanvasEditorPage';

const DETAIL_FIXTURE = {
  id: 'cv1',
  title: 'My canvas',
  description: 'desc',
  viewport_x: 0,
  viewport_y: 0,
  viewport_zoom: 1,
  item_count: 3,
  created_at: '2026-04-10T09:00:00Z',
  updated_at: '2026-04-12T12:00:00Z',
  items: [
    {
      id: 'i-note',
      canvas_id: 'cv1',
      note_id: 'n-1',
      item_type: 'note' as const,
      position_x: 10,
      position_y: 20,
      width: null,
      height: null,
      color: null,
      label: null,
      z_index: 0,
      version: 1,
      last_known_title: null,
      note_title: 'My note',
      note_summary: 'Summary',
      note_content: 'Content',
      created_at: '',
      updated_at: '',
    },
    {
      id: 'i-ghost',
      canvas_id: 'cv1',
      note_id: null,
      item_type: 'note' as const,
      position_x: 30,
      position_y: 40,
      width: null,
      height: null,
      color: null,
      label: null,
      z_index: 0,
      version: 1,
      last_known_title: 'Old note',
      note_title: null,
      note_summary: null,
      note_content: null,
      created_at: '',
      updated_at: '',
    },
    {
      id: 'i-group',
      canvas_id: 'cv1',
      note_id: null,
      item_type: 'group' as const,
      position_x: 100,
      position_y: 100,
      width: 200,
      height: 150,
      color: '#312e81',
      label: 'A group',
      z_index: 0,
      version: 1,
      last_known_title: null,
      note_title: null,
      note_summary: null,
      note_content: null,
      created_at: '',
      updated_at: '',
    },
    {
      id: 'i-text',
      canvas_id: 'cv1',
      note_id: null,
      item_type: 'text' as const,
      position_x: 300,
      position_y: 50,
      width: null,
      height: null,
      color: null,
      label: 'Hello',
      z_index: 0,
      version: 1,
      last_known_title: null,
      note_title: null,
      note_summary: null,
      note_content: null,
      created_at: '',
      updated_at: '',
    },
  ],
  edges: [
    {
      id: 'e1',
      canvas_id: 'cv1',
      source_item_id: 'i-note',
      target_item_id: 'i-group',
      label: null,
      style: 'default' as const,
      created_at: '',
    },
  ],
};

function renderPage(id = 'cv1') {
  return render(
    <MemoryRouter initialEntries={[`/canvas/${id}`]}>
      <Routes>
        <Route path="/canvas/:id" element={<CanvasEditorPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  (canvasApi.getCanvas as ReturnType<typeof vi.fn>).mockResolvedValue(DETAIL_FIXTURE);
});

describe('CanvasEditorPage', () => {
  it('fetches canvas data on mount', async () => {
    renderPage();
    await waitFor(() => expect(canvasApi.getCanvas).toHaveBeenCalledWith('cv1'));
  });

  it('renders reactflow component', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('reactflow')).toBeInTheDocument());
  });

  it('shows the canvas title in the input', async () => {
    renderPage();
    await waitFor(() => {
      const input = screen.getByTestId('canvas-title-input') as HTMLInputElement;
      expect(input.value).toBe('My canvas');
    });
  });

  it('shows the minimap', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('rf-minimap')).toBeInTheDocument());
  });

  it('shows the controls', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('rf-controls')).toBeInTheDocument());
  });

  it('shows the background', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('rf-background')).toBeInTheDocument());
  });

  it('converts items to reactflow nodes', async () => {
    renderPage();
    await waitFor(() => {
      const rf = screen.getByTestId('reactflow');
      expect(rf.getAttribute('data-node-count')).toBe('4');
    });
  });

  it('converts edges to reactflow edges', async () => {
    renderPage();
    await waitFor(() => {
      const rf = screen.getByTestId('reactflow');
      expect(rf.getAttribute('data-edge-count')).toBe('1');
    });
  });

  it('shows loading state before fetch resolves', () => {
    (canvasApi.getCanvas as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByRole('status', { name: /loading canvas/i })).toBeInTheDocument();
  });

  it('shows 404 state for missing canvas', async () => {
    const err = Object.assign(new Error('not found'), { status: 404 });
    (canvasApi.getCanvas as ReturnType<typeof vi.fn>).mockRejectedValue(err);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/canvas not found/i)).toBeInTheDocument();
    });
  });

  it('renders NoteCardNode for note items', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('note-card-node-active')).toBeInTheDocument();
      expect(screen.getByText('My note')).toBeInTheDocument();
    });
  });

  it('renders ghost NoteCardNode for deleted notes', async () => {
    renderPage();
    await waitFor(() => {
      const ghost = screen.getByTestId('note-card-node-ghost');
      expect(ghost).toBeInTheDocument();
      expect(ghost.getAttribute('data-ghost')).toBe('true');
      expect(screen.getByText('Old note')).toBeInTheDocument();
    });
  });

  it('renders GroupNode for group items', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('group-node')).toBeInTheDocument();
      expect(screen.getByText('A group')).toBeInTheDocument();
    });
  });

  it('renders TextNode for text items', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('text-node')).toBeInTheDocument();
      expect(screen.getByText('Hello')).toBeInTheDocument();
    });
  });

  it('shows a back button', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('canvas-back-button')).toBeInTheDocument());
  });

  it('shows toolbar action buttons', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('canvas-add-group')).toBeInTheDocument();
      expect(screen.getByTestId('canvas-add-text')).toBeInTheDocument();
      expect(screen.getByTestId('canvas-auto-layout')).toBeInTheDocument();
    });
  });

  it('canvas container has touch-action: none for mobile pan/pinch', async () => {
    renderPage();
    await waitFor(() => {
      const wrapper = screen.getByTestId('canvas-flow-wrapper');
      expect(wrapper.style.touchAction).toBe('none');
    });
  });

  it('renders the autosave indicator (idle by default)', async () => {
    renderPage();
    await waitFor(() => {
      const ind = screen.getByTestId('canvas-save-indicator');
      expect(ind).toBeInTheDocument();
      expect(ind.getAttribute('data-status')).toBe('idle');
    });
  });

  it('shows the empty state when the canvas has no items', async () => {
    (canvasApi.getCanvas as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...DETAIL_FIXTURE,
      items: [],
      edges: [],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('canvas-empty-state')).toBeInTheDocument();
      expect(screen.getByText(/this canvas is empty/i)).toBeInTheDocument();
      expect(screen.getByText(/Ctrl\+Z undo/i)).toBeInTheDocument();
    });
  });

  it('does not show the empty state when items exist', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('reactflow')).toBeInTheDocument());
    expect(screen.queryByTestId('canvas-empty-state')).not.toBeInTheDocument();
  });

  it('Escape key dispatches without throwing (deselect handler attached)', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('reactflow')).toBeInTheDocument());
    // No assertion needed — just verify the listener handles Escape without error.
    expect(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    }).not.toThrow();
  });

  it('Ctrl+Z key dispatches without throwing (undo handler attached)', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('reactflow')).toBeInTheDocument());
    expect(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', ctrlKey: true }));
    }).not.toThrow();
  });
});
