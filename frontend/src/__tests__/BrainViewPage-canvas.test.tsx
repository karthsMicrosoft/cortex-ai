/**
 * BrainViewPage-canvas.test.tsx — PR C tests for "Open as Canvas" button.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

// Mock three.js
vi.mock('three', () => {
  const mockMaterial = { color: 0, transparent: false, opacity: 1, wireframe: false, map: null, depthWrite: true };
  const mockMesh = { add: vi.fn(), position: { set: vi.fn() }, scale: { set: vi.fn(), setScalar: vi.fn() }, traverse: vi.fn(), isMesh: true, material: mockMaterial };
  return {
    SphereGeometry: vi.fn(),
    MeshLambertMaterial: vi.fn(() => ({ ...mockMaterial })),
    MeshBasicMaterial: vi.fn(() => ({ ...mockMaterial })),
    Mesh: vi.fn(() => ({ ...mockMesh })),
    Color: vi.fn(),
    SpriteMaterial: vi.fn(() => ({ ...mockMaterial })),
    Sprite: vi.fn(() => ({ position: { set: vi.fn() }, scale: { set: vi.fn() } })),
    CanvasTexture: vi.fn(() => ({ needsUpdate: false })),
    AmbientLight: vi.fn(() => ({})),
    DirectionalLight: vi.fn(() => ({ position: { set: vi.fn() } })),
  };
});

vi.mock('three/examples/jsm/loaders/GLTFLoader.js', () => ({
  GLTFLoader: vi.fn().mockImplementation(() => ({
    load: vi.fn(),
  })),
}));

// Mock react-force-graph-3d
vi.mock('react-force-graph-3d', () => {
  const React = require('react');
  const ForceGraph3DMock = React.forwardRef((props: Record<string, unknown>, ref: React.Ref<unknown>) => {
    const graphData = (props.graphData ?? { nodes: [], links: [] }) as {
      nodes: { id: string; label: string; category: string }[];
      links: unknown[];
    };

    React.useImperativeHandle(ref, () => ({
      scene: () => ({ add: () => {} }),
      renderer: () => ({ setPixelRatio: () => {} }),
      d3Force: () => ({ strength: () => {} }),
      d3ReheatSimulation: () => {},
    }));

    return React.createElement('div', {
      'data-testid': 'force-graph',
      'data-node-count': graphData?.nodes?.length ?? 0,
    },
      React.createElement('ul', { 'data-testid': 'graph-nodes' },
        (graphData?.nodes ?? []).map((n: { id: string; label: string }) =>
          React.createElement('li', {
            key: n.id,
            'data-testid': `node-${n.id}`,
          }, n.label)
        )
      )
    );
  });
  ForceGraph3DMock.displayName = 'ForceGraph3DMock';
  return { default: ForceGraph3DMock };
});

const { mockNavigate } = vi.hoisted(() => ({ mockNavigate: vi.fn() }));
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  );
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../api/canvas', () => ({
  createCanvas: vi.fn(),
  addCanvasItem: vi.fn(),
}));

import * as canvasApi from '../api/canvas';
const mockedCreate = vi.mocked(canvasApi.createCanvas);
const mockedAddItem = vi.mocked(canvasApi.addCanvasItem);

const MOCK_GRAPH = {
  nodes: [
    { id: 'n1', label: 'Note 1', category: 'Music' },
    { id: 'n2', label: 'Note 2', category: 'Ideas' },
    { id: 'n3', label: 'Note 3', category: 'Fitness' },
  ],
  links: [],
};

function setupFetch(data = MOCK_GRAPH) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (url.includes('insights/graph')) {
        return Promise.resolve({ ok: true, status: 200, json: async () => data });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
    }),
  );
}

import BrainViewPage from '../pages/BrainViewPage';

beforeEach(() => {
  vi.clearAllMocks();
  setupFetch();
});

describe('BrainViewPage — Open as Canvas (PR C)', () => {
  it('renders the "Open as Canvas" button', async () => {
    render(
      <MemoryRouter>
        <BrainViewPage />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('brain-view-open-as-canvas')).toBeInTheDocument();
  });

  it('creates a canvas and adds graph nodes on click, then navigates', async () => {
    mockedCreate.mockResolvedValueOnce({
      id: 'new-canvas',
      title: 'Brain View — today',
      description: null,
      viewport_x: 0,
      viewport_y: 0,
      viewport_zoom: 1,
      item_count: 0,
      created_at: '2026-05-01T00:00:00Z',
      updated_at: '2026-05-01T00:00:00Z',
    });
    mockedAddItem.mockResolvedValue({
      id: 'i',
      canvas_id: 'new-canvas',
      note_id: 'n1',
      item_type: 'note',
      position_x: 0,
      position_y: 0,
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
    });

    render(
      <MemoryRouter>
        <BrainViewPage />
      </MemoryRouter>,
    );

    // Wait for nodes to render
    await screen.findByTestId('node-n1');

    fireEvent.click(screen.getByTestId('brain-view-open-as-canvas'));

    await waitFor(() => {
      expect(mockedCreate).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(mockedAddItem).toHaveBeenCalledTimes(3);
    });
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/canvas/new-canvas');
    });
  });
});
