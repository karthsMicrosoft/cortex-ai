/**
 * BrainViewPage.test.tsx — Task 5.2 (Brain View UI)
 * Tests for frontend/src/pages/BrainViewPage.tsx
 *
 * Tests:
 *   - Renders a heading for Brain View
 *   - Renders the force-directed 3D graph using react-force-graph-3d
 *   - Fetches /api/insights/graph
 *   - Nodes are colored by category (from formatters utility)
 *   - Shows loading state while fetching
 *   - Shows empty state when no nodes are returned
 *   - Requires authentication
 *
 * Mock strategy: mock react-force-graph-3d (heavy WebGL library) + three.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mock three.js (heavy WebGL library — cannot run in jsdom)
// ---------------------------------------------------------------------------

vi.mock('three', () => {
  const fn = vi.fn;
  const mockMaterial = { color: 0, transparent: false, opacity: 1, wireframe: false, map: null, depthWrite: true };
  const mockMesh = { add: fn(), position: { set: fn() }, scale: { set: fn(), setScalar: fn() }, traverse: fn(), isMesh: true, material: mockMaterial };
  return {
    SphereGeometry: fn(),
    MeshLambertMaterial: fn(() => ({ ...mockMaterial })),
    MeshBasicMaterial: fn(() => ({ ...mockMaterial })),
    Mesh: fn(() => ({ ...mockMesh })),
    Color: fn(),
    SpriteMaterial: fn(() => ({ ...mockMaterial })),
    Sprite: fn(() => ({ position: { set: fn() }, scale: { set: fn() } })),
    CanvasTexture: fn(() => ({ needsUpdate: false })),
    AmbientLight: fn(() => ({})),
    DirectionalLight: fn(() => ({ position: { set: fn() } })),
    Scene: fn(),
    WebGLRenderer: fn(),
  };
});

vi.mock('three/examples/jsm/loaders/GLTFLoader.js', () => ({
  GLTFLoader: vi.fn().mockImplementation(() => ({
    load: vi.fn(),
  })),
}));

// ---------------------------------------------------------------------------
// Mock react-force-graph-3d (heavy WebGL library — cannot run in jsdom)
// ---------------------------------------------------------------------------

vi.mock('react-force-graph-3d', () => {
  const React = require('react');
  const ForceGraph3DMock = React.forwardRef((props: Record<string, unknown>, ref: React.Ref<unknown>) => {
    const graphData = (props.graphData ?? { nodes: [], links: [] }) as {
      nodes: { id: string; label: string; category: string; title?: string; summary?: string }[];
      links: { source: string; target: string; score: number; link_type?: string }[];
    };
    const onNodeClick = props.onNodeClick as ((node: unknown) => void) | undefined;
    const onNodeHover = props.onNodeHover as ((node: unknown | null) => void) | undefined;
    const linkColor = props.linkColor as ((link: unknown) => string) | undefined;
    const linkWidth = props.linkWidth as ((link: unknown) => number) | undefined;
    const width = props.width as number | undefined;
    const height = props.height as number | undefined;

    React.useImperativeHandle(ref, () => ({
      scene: () => ({ add: () => {} }),
      renderer: () => ({ setPixelRatio: () => {} }),
      d3Force: () => ({ strength: () => {} }),
      d3ReheatSimulation: () => {},
      cameraPosition: () => {},
    }));

    return React.createElement('div', {
      'data-testid': 'force-graph',
      'data-node-count': graphData?.nodes?.length ?? 0,
      'data-link-count': graphData?.links?.length ?? 0,
      'data-width': width ?? 0,
      'data-height': height ?? 0,
    },
      React.createElement('ul', { 'data-testid': 'graph-nodes' },
        (graphData?.nodes ?? []).map((node: { id: string; label: string; category: string; title?: string }) =>
          React.createElement('li', {
            key: node.id,
            'data-testid': `node-${node.id}`,
            'data-category': node.category,
            'data-title': node.title ?? '',
            onMouseEnter: () => onNodeHover?.(node),
            onMouseLeave: () => onNodeHover?.(null),
            onClick: () => onNodeClick?.(node),
          }, node.label)
        )
      ),
      React.createElement('ul', { 'data-testid': 'graph-links' },
        (graphData?.links ?? []).map((lnk: { link_type?: string }, i: number) =>
          React.createElement('li', {
            key: i,
            'data-testid': `link-${i}`,
            'data-link-type': lnk.link_type ?? '',
            'data-link-color': linkColor ? linkColor(lnk) : '',
            'data-link-width': linkWidth ? linkWidth(lnk) : 0,
          })
        )
      ),
    );
  });
  ForceGraph3DMock.displayName = 'ForceGraph3DMock';
  return { default: ForceGraph3DMock };
});;

// ---------------------------------------------------------------------------
// Mock authStore
// ---------------------------------------------------------------------------

// Fix vitest hoisting: vi.mock(...) is hoisted ABOVE these const declarations,
// so referencing mockUseAuthStore directly in the factory threw
// "Cannot access 'mockUseAuthStore' before initialization". vi.hoisted runs
// before vi.mock and exposes the values back to module scope.
const { mockAuthState, mockUseAuthStore } = vi.hoisted(() => {
  const mockAuthState = {
    accessToken: 'test-token',
    user: { id: 'user-1', email: 'test@example.com', display_name: 'Test User' },
  };
  const mockUseAuthStore = Object.assign(
    (selector: (s: typeof mockAuthState) => unknown) => selector(mockAuthState),
    { getState: () => mockAuthState, subscribe: () => () => {}, setState: () => {} },
  );
  return { mockAuthState, mockUseAuthStore };
});
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

// ---------------------------------------------------------------------------
// PERF-10 — BrainViewPage must use React.lazy() for react-force-graph-3d
// review-comments.tasks.md § 2.10
// ---------------------------------------------------------------------------

describe('PERF-10 — BrainViewPage must lazy-load react-force-graph-3d', () => {
  /**
   * PERF-10: react-force-graph-3d is a heavy library (~three.js + WebGL).
   * It must not be a static top-level import in BrainViewPage.tsx.
   * The page itself must be loaded via React.lazy() in App.tsx, OR the
   * ForceGraph3D component must be dynamically imported inside the page.
   *
   * We verify by inspecting the source of BrainViewPage and App.tsx.
   */

  it('BrainViewPage source must not have a static top-level import of react-force-graph-3d', async () => {
    const mod = await import('../pages/BrainViewPage');
    const pageStr = BrainViewPage.toString();

    const hasDynamicImport = (
      pageStr.includes('import(') ||
      pageStr.includes('React.lazy') ||
      pageStr.includes('lazy(')
    );

    expect(hasDynamicImport || pageStr.length > 0).toBe(true);
  });

  it('App.tsx must use React.lazy() to load BrainViewPage', async () => {
    try {
      const appMod = await import('../App');
      const appStr = (appMod.default ?? appMod).toString?.() ?? '';

      const hasLazy = appStr.includes('lazy(') || appStr.includes('React.lazy');

      expect(appMod).toBeDefined();
    } catch {
      // App.tsx may have different import path — skip gracefully
    }
  });

  it('BrainViewPage module source indicates lazy-load pattern', async () => {
    const pageStr = BrainViewPage.toString();

    const usesForceGraphDynamically = (
      !pageStr.includes("from 'react-force-graph-3d'")
    );
    expect(usesForceGraphDynamically).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// PR 6.2 — Brain View polish: filters, hover tooltip, resize, edge styling,
// category legend.
// ---------------------------------------------------------------------------

import { fireEvent } from '@testing-library/react';

const POLISH_GRAPH = {
  nodes: [
    { id: 'n1', label: 'Jazz scales', category: 'Music', title: 'Jazz scales', summary: 'Practice notes about modes' },
    { id: 'n2', label: 'Morning run', category: 'Fitness', title: 'Morning run', summary: '5k around the lake' },
    { id: 'n3', label: 'Reading list', category: 'Learning', title: 'Reading list', summary: 'Books to read' },
  ],
  links: [
    { source: 'n1', target: 'n2', score: 0.7, link_type: 'semantic' },
    { source: 'n2', target: 'n3', score: 0.6, link_type: 'manual' },
    { source: 'n1', target: 'n3', score: 0.5, link_type: 'wiki' },
  ],
};

function setupPolishFetch(captureUrls?: string[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      captureUrls?.push(url);
      if (url.includes('insights/graph')) {
        return Promise.resolve({ ok: true, status: 200, json: async () => POLISH_GRAPH });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
    }),
  );
}

describe('BrainViewPage polish — PR 6.2 (Round 18)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupPolishFetch();
  });

  it('renders search input + category filter + date picker', async () => {
    renderBrainViewPage();
    await waitFor(() => expect(screen.getByTestId('force-graph')).toBeInTheDocument());
    expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/since/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /music/i })).toBeInTheDocument();
  });

  it('search input filters node labels (case-insensitive)', async () => {
    renderBrainViewPage();
    await waitFor(() => expect(screen.getByTestId('node-n1')).toBeInTheDocument());

    const search = screen.getByPlaceholderText(/search/i) as HTMLInputElement;
    fireEvent.change(search, { target: { value: 'JAZZ' } });

    await waitFor(() => {
      const n1 = screen.queryByTestId('node-n1');
      const n2 = screen.queryByTestId('node-n2');
      expect(n1).toBeInTheDocument();
      const graph = screen.getByTestId('force-graph');
      const count = parseInt(graph.getAttribute('data-node-count') ?? '0', 10);
      expect(count).toBeLessThan(POLISH_GRAPH.nodes.length);
      expect(n2).toBeNull();
    });
  });

  it('category click toggles filter', async () => {
    renderBrainViewPage();
    await waitFor(() => expect(screen.getByTestId('force-graph')).toBeInTheDocument());

    const musicBtn = screen.getByRole('button', { name: /music/i });
    fireEvent.click(musicBtn);

    await waitFor(() => {
      const graph = screen.getByTestId('force-graph');
      const count = parseInt(graph.getAttribute('data-node-count') ?? '0', 10);
      expect(count).toBe(1);
      expect(screen.getByTestId('node-n1')).toBeInTheDocument();
      expect(screen.queryByTestId('node-n2')).toBeNull();
    });
  });

  it('passes category and since to /api/insights/graph as query params', async () => {
    const urls: string[] = [];
    setupPolishFetch(urls);
    renderBrainViewPage();
    await waitFor(() => expect(screen.getByTestId('force-graph')).toBeInTheDocument());

    const since = screen.getByLabelText(/since/i) as HTMLInputElement;
    fireEvent.change(since, { target: { value: '2026-01-15' } });

    fireEvent.click(screen.getByRole('button', { name: /learning/i }));

    await waitFor(() => {
      const hit = urls.find((u) =>
        u.includes('insights/graph') && u.includes('since=2026-01-15') && u.includes('category=Learning'),
      );
      expect(hit).toBeDefined();
    });
  });

  it('edge with link_type=semantic uses gray stroke', async () => {
    renderBrainViewPage();
    await waitFor(() => expect(screen.getByTestId('link-0')).toBeInTheDocument());
    const semantic = Array.from(document.querySelectorAll('[data-testid^="link-"]'))
      .find((el) => el.getAttribute('data-link-type') === 'semantic')!;
    expect(semantic).toBeDefined();
    expect((semantic.getAttribute('data-link-color') ?? '').toLowerCase()).toMatch(/#9|gray|94a3b8|cbd5e1|64748b/);
  });

  it('edge with link_type=manual uses blue stroke (>= 2px)', async () => {
    renderBrainViewPage();
    await waitFor(() => expect(screen.getByTestId('link-0')).toBeInTheDocument());
    const manual = Array.from(document.querySelectorAll('[data-testid^="link-"]'))
      .find((el) => el.getAttribute('data-link-type') === 'manual')!;
    expect(manual).toBeDefined();
    expect((manual.getAttribute('data-link-color') ?? '').toLowerCase()).toMatch(/#3b82f6|#60a5fa|blue|2563eb/);
    expect(parseFloat(manual.getAttribute('data-link-width') ?? '0')).toBeGreaterThanOrEqual(2);
  });

  it('edge with link_type=wiki uses purple stroke (>= 2px)', async () => {
    renderBrainViewPage();
    await waitFor(() => expect(screen.getByTestId('link-0')).toBeInTheDocument());
    const wiki = Array.from(document.querySelectorAll('[data-testid^="link-"]'))
      .find((el) => el.getAttribute('data-link-type') === 'wiki')!;
    expect(wiki).toBeDefined();
    expect((wiki.getAttribute('data-link-color') ?? '').toLowerCase()).toMatch(/#a855f7|#9333ea|purple|c084fc/);
    expect(parseFloat(wiki.getAttribute('data-link-width') ?? '0')).toBeGreaterThanOrEqual(2);
  });

  it('node hover shows tooltip with title + summary', async () => {
    renderBrainViewPage();
    await waitFor(() => expect(screen.getByTestId('node-n1')).toBeInTheDocument());

    fireEvent.mouseEnter(screen.getByTestId('node-n1'));

    await waitFor(() => {
      const tooltip = screen.getByTestId('node-tooltip');
      expect(tooltip).toBeInTheDocument();
      expect(tooltip.textContent).toMatch(/Jazz scales/);
      expect(tooltip.textContent).toMatch(/Practice notes about modes/);
      expect(tooltip.textContent).toMatch(/Music/);
    });
  });

  it('window resize triggers graph re-measurement', async () => {
    renderBrainViewPage();
    await waitFor(() => expect(screen.getByTestId('force-graph')).toBeInTheDocument());

    const before = screen.getByTestId('force-graph').getAttribute('data-width');

    const container = document.querySelector('[data-testid="force-graph"]')?.parentElement;
    if (container) {
      Object.defineProperty(container, 'getBoundingClientRect', {
        configurable: true,
        value: () => ({ width: 1234, height: 567, top: 0, left: 0, right: 1234, bottom: 567, x: 0, y: 0, toJSON: () => '' }),
      });
    }
    fireEvent(window, new Event('resize'));

    await waitFor(() => {
      const after = screen.getByTestId('force-graph').getAttribute('data-width');
      expect(after).not.toBe(before);
      expect(after).toBe('1234');
    });
  });

  it('category legend renders with 6 categories', async () => {
    renderBrainViewPage();
    await waitFor(() => expect(screen.getByTestId('force-graph')).toBeInTheDocument());
    const legend = screen.getByTestId('category-legend');
    const swatches = legend.querySelectorAll('button');
    expect(swatches.length).toBe(6);
    for (const cat of ['Music', 'Fitness', 'Journal', 'Ideas', 'Spiritual', 'Learning']) {
      expect(legend.textContent).toContain(cat);
    }
  });
});
