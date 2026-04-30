/**
 * BrainViewPage.test.tsx — Task 5.2 (Brain View UI)
 * TDD red-phase tests for frontend/src/pages/BrainViewPage.tsx
 *
 * Tests:
 *   - Renders a heading for Brain View
 *   - Renders the force-directed graph using react-force-graph-2d
 *   - Fetches /api/insights/graph
 *   - Nodes are colored by category (from formatters utility)
 *   - Shows loading state while fetching
 *   - Shows empty state when no nodes are returned
 *   - Requires authentication
 *
 * Mock strategy: mock react-force-graph-2d (heavy canvas library).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mock react-force-graph-2d (heavy canvas library — cannot run in jsdom)
// ---------------------------------------------------------------------------

vi.mock('react-force-graph-2d', () => ({
  default: ({
    graphData,
    nodeLabel,
    nodeColor,
    linkColor,
    onNodeClick,
    width,
    height,
  }: {
    graphData: { nodes: { id: string; label: string; category: string }[]; links: { source: string; target: string; score: number }[] };
    nodeLabel?: (node: { id: string; label: string; category: string }) => string;
    nodeColor?: (node: { id: string; label: string; category: string }) => string;
    linkColor?: () => string;
    onNodeClick?: (node: { id: string; label: string; category: string }) => void;
    width?: number;
    height?: number;
  }) => (
    <div
      data-testid="force-graph"
      data-node-count={graphData?.nodes?.length ?? 0}
      data-link-count={graphData?.links?.length ?? 0}
    >
      <ul data-testid="graph-nodes">
        {(graphData?.nodes ?? []).map((node) => (
          <li key={node.id} data-testid={`node-${node.id}`} data-category={node.category}>
            {node.label}
          </li>
        ))}
      </ul>
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Mock authStore
// ---------------------------------------------------------------------------

const mockAuthState = {
  accessToken: 'test-token',
  user: { id: 'user-1', email: 'test@example.com', display_name: 'Test User' },
};
const mockUseAuthStore = Object.assign(
  (selector: (s: typeof mockAuthState) => unknown) => selector(mockAuthState),
  { getState: () => mockAuthState, subscribe: vi.fn(), setState: vi.fn() },
);
vi.mock('../store/authStore', () => ({ useAuthStore: mockUseAuthStore }));

// ---------------------------------------------------------------------------
// Mock graph data
// ---------------------------------------------------------------------------

const MOCK_GRAPH_DATA = {
  nodes: [
    { id: 'note-1', label: 'Jazz improvisation ideas', category: 'Music' },
    { id: 'note-2', label: 'Morning run stats', category: 'Fitness' },
    { id: 'note-3', label: 'Startup idea about AI', category: 'Ideas' },
  ],
  links: [
    { source: 'note-1', target: 'note-2', score: 0.82 },
    { source: 'note-2', target: 'note-3', score: 0.75 },
  ],
};

// ---------------------------------------------------------------------------
// Mock fetch
// ---------------------------------------------------------------------------

function setupFetchMocks(graphData = MOCK_GRAPH_DATA) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (url.includes('insights/graph')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => graphData,
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
    }),
  );
}

// ---------------------------------------------------------------------------
// Import component under test
// ---------------------------------------------------------------------------

import BrainViewPage from '../pages/BrainViewPage';

function renderBrainViewPage() {
  return render(
    <MemoryRouter>
      <BrainViewPage />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('BrainViewPage (Task 5.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupFetchMocks();
  });

  // --- Page structure ---

  it('renders a Brain View heading', async () => {
    renderBrainViewPage();
    await waitFor(() => {
      const heading = screen.getByRole('heading', { name: /brain view|knowledge graph|graph/i });
      expect(heading).toBeInTheDocument();
    });
  });

  // --- Force graph rendering ---

  it('renders the force-directed graph component', async () => {
    renderBrainViewPage();
    await waitFor(() => {
      expect(screen.getByTestId('force-graph')).toBeInTheDocument();
    });
  });

  it('passes node data to the force graph', async () => {
    renderBrainViewPage();
    await waitFor(() => {
      const graph = screen.getByTestId('force-graph');
      const nodeCount = parseInt(graph.getAttribute('data-node-count') ?? '0', 10);
      expect(nodeCount).toBe(MOCK_GRAPH_DATA.nodes.length);
    });
  });

  it('passes link data to the force graph', async () => {
    renderBrainViewPage();
    await waitFor(() => {
      const graph = screen.getByTestId('force-graph');
      const linkCount = parseInt(graph.getAttribute('data-link-count') ?? '0', 10);
      expect(linkCount).toBe(MOCK_GRAPH_DATA.links.length);
    });
  });

  it('renders node labels in the graph', async () => {
    renderBrainViewPage();
    await waitFor(() => {
      expect(screen.getByText(/Jazz improvisation ideas/i)).toBeInTheDocument();
      expect(screen.getByText(/Morning run stats/i)).toBeInTheDocument();
      expect(screen.getByText(/Startup idea about AI/i)).toBeInTheDocument();
    });
  });

  // --- Category-based node coloring ---

  it('nodes carry category data for color mapping', async () => {
    renderBrainViewPage();
    await waitFor(() => {
      const musicNode = screen.getByTestId('node-note-1');
      expect(musicNode.getAttribute('data-category')).toBe('Music');

      const fitnessNode = screen.getByTestId('node-note-2');
      expect(fitnessNode.getAttribute('data-category')).toBe('Fitness');
    });
  });

  // --- API fetch ---

  it('fetches graph data from /api/insights/graph', async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => url.includes('insights/graph') ? MOCK_GRAPH_DATA : {},
      });
    });
    vi.stubGlobal('fetch', fetchSpy);

    renderBrainViewPage();

    await waitFor(() => {
      const calls = fetchSpy.mock.calls.map(([url]: [string]) => url);
      const graphCall = calls.find((url: string) => url.includes('insights/graph'));
      expect(graphCall).toBeDefined();
    });
  });

  it('sends Authorization header with graph fetch', async () => {
    const fetchSpy = vi.fn().mockImplementation((url: string) => {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => url.includes('insights/graph') ? MOCK_GRAPH_DATA : {},
      });
    });
    vi.stubGlobal('fetch', fetchSpy);

    renderBrainViewPage();

    await waitFor(() => {
      const graphCall = fetchSpy.mock.calls.find(([url]: [string]) =>
        url.includes('insights/graph'),
      );
      expect(graphCall).toBeDefined();
      if (graphCall) {
        const [, options] = graphCall as [string, RequestInit];
        const headers = options?.headers ?? {};
        expect(JSON.stringify(headers)).toContain('Bearer');
      }
    });
  });

  // --- Loading state ---

  it('shows a loading indicator while fetching graph data', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})));
    renderBrainViewPage();
    expect(document.body.textContent).toMatch(/loading|…|\.\.\./i);
  });

  // --- Empty state ---

  it('shows an empty state when no nodes are returned', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ nodes: [], links: [] }),
        }),
      ),
    );

    renderBrainViewPage();

    await waitFor(() => {
      expect(document.body.textContent).toMatch(/no notes|empty|add notes|no connections/i);
    });
  });

  // --- Error state ---

  it('shows an error message when the graph fetch fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() =>
        Promise.resolve({
          ok: false,
          status: 500,
          json: async () => ({ detail: 'Internal Server Error' }),
        }),
      ),
    );

    renderBrainViewPage();

    await waitFor(() => {
      expect(document.body.textContent).toMatch(/error|failed|could not load/i);
    });
  });
});
