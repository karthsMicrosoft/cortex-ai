import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Layout, Loader2, RefreshCw, Search } from 'lucide-react';
import ForceGraph2D from 'react-force-graph-2d';
import { apiGet } from '../api/client';
import { addCanvasItem, createCanvas } from '../api/canvas';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface GraphNode {
  id: string;
  label: string;
  category: string;
  title?: string | null;
  summary?: string | null;
}

interface GraphLink {
  source: string;
  target: string;
  score: number;
  link_type?: string;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

interface FGNode extends GraphNode {
  x?: number;
  y?: number;
}

// ---------------------------------------------------------------------------
// Category palette
// ---------------------------------------------------------------------------

const CATEGORY_HEX: Record<string, string> = {
  Music: '#a855f7',
  Fitness: '#22c55e',
  Journal: '#3b82f6',
  Ideas: '#6366f1',
  Spiritual: '#f59e0b',
  Learning: '#06b6d4',
};

const ALL_CATEGORIES = Object.keys(CATEGORY_HEX);

function categoryToHex(category: string): string {
  return CATEGORY_HEX[category] ?? '#94a3b8';
}

// ---------------------------------------------------------------------------
// Edge styling per link_type
// ---------------------------------------------------------------------------

const LINK_STYLE: Record<string, { color: string; width: number; dash: number[] | null }> = {
  semantic: { color: '#94a3b8', width: 1, dash: [4, 3] }, // dashed gray
  manual:   { color: '#3b82f6', width: 2, dash: null },    // solid blue
  wiki:     { color: '#a855f7', width: 2, dash: null },    // solid purple
};

function styleFor(lt: string | undefined) {
  return LINK_STYLE[lt ?? 'semantic'] ?? LINK_STYLE.semantic;
}

// ---------------------------------------------------------------------------
// BrainViewPage
// ---------------------------------------------------------------------------

export default function BrainViewPage(): React.ReactElement {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 400, height: 600 });

  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [activeCategories, setActiveCategories] = useState<Set<string>>(new Set());
  const [since, setSince] = useState<string>('');

  const [hoverNode, setHoverNode] = useState<FGNode | null>(null);
  const [hoverPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportWarning, setExportWarning] = useState<string | null>(null);

  // ---- Resize observer + window resize ----
  const remeasure = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setDimensions({ width: rect.width || 400, height: rect.height || 600 });
  }, []);

  useEffect(() => {
    remeasure();
    const onResize = () => remeasure();
    window.addEventListener('resize', onResize);

    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined' && containerRef.current) {
      ro = new ResizeObserver(() => remeasure());
      ro.observe(containerRef.current);
    }
    return () => {
      window.removeEventListener('resize', onResize);
      ro?.disconnect();
    };
  }, [remeasure]);

  // ---- Fetch graph data, refetch on category/since change ----
  useEffect(() => {
    setIsLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (activeCategories.size === 1) {
      params.set('category', Array.from(activeCategories)[0]);
    }
    if (since) params.set('since', since);
    const qs = params.toString();
    const url = `/api/insights/graph${qs ? `?${qs}` : ''}`;

    void apiGet<GraphData>(url)
      .then((data) => setGraphData(data))
      .catch((err: Error) => setError(err.message))
      .finally(() => setIsLoading(false));
  }, [activeCategories, since]);

  // ---- Client-side derived filtered graph ----
  const filteredGraph = useMemo<GraphData>(() => {
    const q = search.trim().toLowerCase();
    let nodes = graphData.nodes;
    if (activeCategories.size > 0) {
      nodes = nodes.filter((n) => activeCategories.has(n.category));
    }
    if (q) {
      nodes = nodes.filter((n) => {
        const hay = `${n.label ?? ''} ${n.title ?? ''}`.toLowerCase();
        return hay.includes(q);
      });
    }
    const ids = new Set(nodes.map((n) => n.id));
    const links = graphData.links.filter(
      (l) => ids.has(typeof l.source === 'string' ? l.source : (l.source as { id: string }).id) &&
             ids.has(typeof l.target === 'string' ? l.target : (l.target as { id: string }).id),
    );
    return { nodes, links };
  }, [graphData, search, activeCategories]);

  const handleNodeClick = useCallback(
    (node: FGNode) => {
      navigate(`/note/${node.id}`);
    },
    [navigate],
  );

  const handleOpenAsCanvas = useCallback(async () => {
    if (isExporting) return;
    setIsExporting(true);
    setExportError(null);
    setExportWarning(null);
    try {
      const nodes = filteredGraph.nodes as FGNode[];
      const MAX_ITEMS = 50;
      const cap = nodes.slice(0, MAX_ITEMS);
      if (nodes.length > MAX_ITEMS) {
        setExportWarning(
          `Only the first ${MAX_ITEMS} of ${nodes.length} nodes were added.`,
        );
      }
      const dateStr = new Date().toLocaleDateString();
      const canvas = await createCanvas({ title: `Brain View — ${dateStr}` });
      for (const node of cap) {
        try {
          await addCanvasItem(canvas.id, {
            note_id: node.id,
            item_type: 'note',
            position_x: node.x ?? 0,
            position_y: node.y ?? 0,
          });
        } catch {
          // Skip nodes that fail (e.g., note already deleted).
        }
      }
      navigate(`/canvas/${canvas.id}`);
    } catch (err: unknown) {
      setExportError(err instanceof Error ? err.message : 'Failed to create canvas');
    } finally {
      setIsExporting(false);
    }
  }, [filteredGraph, isExporting, navigate]);

  const handleNodeHover = useCallback((node: FGNode | null) => {
    setHoverNode(node);
  }, []);

  const toggleCategory = (cat: string) => {
    setActiveCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) {
        next.delete(cat);
      } else {
        next.add(cat);
      }
      return next;
    });
  };

  const paintNode = useCallback(
    (node: FGNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const r = 6;
      const fontSize = Math.max(8, 10 / globalScale);
      const hex = categoryToHex(node.category);

      ctx.beginPath();
      ctx.arc(node.x ?? 0, node.y ?? 0, r, 0, 2 * Math.PI);
      ctx.fillStyle = hex;
      ctx.fill();
      ctx.strokeStyle = '#1e293b';
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.font = `${fontSize}px sans-serif`;
      ctx.fillStyle = '#cbd5e1';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      const label =
        node.label.length > 20 ? `${node.label.slice(0, 20)}…` : node.label;
      ctx.fillText(label, node.x ?? 0, (node.y ?? 0) + r + 2);
    },
    [],
  );

  return (
    <div className="flex min-h-screen flex-col bg-[#0F172A]">
      {/* Header */}
      <header className="flex items-center gap-3 border-b border-slate-700 px-4 py-3">
        <button
          type="button"
          aria-label="Go back"
          onClick={() => navigate(-1)}
          className="rounded-lg p-1 text-slate-400 hover:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <h1 className="text-lg font-semibold text-slate-100">Brain View</h1>
        {!isLoading && (
          <span className="ml-auto text-xs text-slate-500">
            {filteredGraph.nodes.length} nodes · {filteredGraph.links.length} links
          </span>
        )}
      </header>

      {/* Toolbar: search + since */}
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-800 px-4 py-2">
        <div className="relative flex items-center">
          <Search className="absolute left-2 h-3.5 w-3.5 text-slate-500" aria-hidden="true" />
          <input
            type="text"
            placeholder="Search notes…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="rounded-md border border-slate-700 bg-slate-900 py-1 pl-7 pr-2 text-xs text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <label className="flex items-center gap-1 text-xs text-slate-400">
          <span>Since</span>
          <input
            type="date"
            aria-label="Since"
            value={since}
            onChange={(e) => setSince(e.target.value)}
            className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none"
          />
        </label>
        {activeCategories.size > 0 && (
          <button
            type="button"
            onClick={() => setActiveCategories(new Set())}
            className="text-xs text-indigo-400 hover:text-indigo-300"
          >
            Clear filters
          </button>
        )}
        <button
          type="button"
          onClick={() => void handleOpenAsCanvas()}
          disabled={isExporting || filteredGraph.nodes.length === 0}
          data-testid="brain-view-open-as-canvas"
          className="ml-auto flex items-center gap-1.5 rounded-md border border-indigo-600 bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isExporting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <Layout className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          Open as Canvas
        </button>
      </div>

      {(exportError || exportWarning) && (
        <div
          data-testid="brain-view-export-status"
          className={`border-b px-4 py-1 text-xs ${
            exportError
              ? 'border-red-700 bg-red-900/30 text-red-200'
              : 'border-amber-700 bg-amber-900/30 text-amber-200'
          }`}
        >
          {exportError ?? exportWarning}
        </div>
      )}

      {/* Category legend (also acts as filter toggles) */}
      <div
        data-testid="category-legend"
        className="flex flex-wrap gap-2 border-b border-slate-800 px-4 py-2"
      >
        {ALL_CATEGORIES.map((cat) => {
          const hex = CATEGORY_HEX[cat];
          const active = activeCategories.has(cat);
          return (
            <button
              key={cat}
              type="button"
              aria-label={cat}
              aria-pressed={active}
              onClick={() => toggleCategory(cat)}
              className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs transition ${
                active
                  ? 'border-indigo-400 bg-slate-800 text-slate-100'
                  : 'border-slate-700 text-slate-400 hover:text-slate-200'
              }`}
            >
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: hex }}
              />
              {cat}
            </button>
          );
        })}
      </div>

      {/* Graph canvas */}
      <div ref={containerRef} className="relative flex-1">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
              Loading graph…
            </div>
          </div>
        )}

        {!isLoading && error && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {!isLoading && !error && filteredGraph.nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-sm text-slate-500">
              No notes yet. Capture some notes to see your brain map.
            </p>
          </div>
        )}

        {!isLoading && !error && filteredGraph.nodes.length > 0 && (
          <>
            <ForceGraph2D
              width={dimensions.width}
              height={dimensions.height}
              graphData={filteredGraph}
              nodeId="id"
              linkSource="source"
              linkTarget="target"
              nodeCanvasObject={
                paintNode as (
                  node: object,
                  ctx: CanvasRenderingContext2D,
                  globalScale: number,
                ) => void
              }
              nodeCanvasObjectMode={() => 'replace'}
              linkColor={(link) => styleFor((link as GraphLink).link_type).color}
              linkWidth={(link) => styleFor((link as GraphLink).link_type).width}
              linkLineDash={(link) => styleFor((link as GraphLink).link_type).dash}
              onNodeClick={(node) => handleNodeClick(node as FGNode)}
              onNodeHover={(node) => {
                handleNodeHover((node as FGNode | null) ?? null);
              }}
              backgroundColor="#0F172A"
              nodePointerAreaPaint={(node, color, ctx) => {
                const n = node as FGNode;
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(n.x ?? 0, n.y ?? 0, 8, 0, 2 * Math.PI);
                ctx.fill();
              }}
            />

            {hoverNode && (
              <div
                data-testid="node-tooltip"
                className="pointer-events-none absolute max-w-xs rounded-md border border-slate-700 bg-slate-900/95 p-3 text-xs text-slate-200 shadow-lg"
                style={{ left: hoverPos.x + 12, top: hoverPos.y + 12 }}
              >
                <div className="font-semibold text-slate-100">
                  {hoverNode.title ?? hoverNode.label}
                </div>
                {hoverNode.summary && (
                  <p className="mt-1 line-clamp-3 text-slate-300">{hoverNode.summary}</p>
                )}
                <div className="mt-1 inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-slate-400">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ backgroundColor: categoryToHex(hoverNode.category) }}
                  />
                  {hoverNode.category}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
