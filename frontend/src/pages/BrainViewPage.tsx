import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import ForceGraph2D from 'react-force-graph-2d';
import { apiGet } from '../api/client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface GraphNode {
  id: string;
  label: string;
  category: string;
}

interface GraphLink {
  source: string;
  target: string;
  score: number;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

// Internal ForceGraph2D node type (includes runtime x/y/vx/vy etc.)
interface FGNode extends GraphNode {
  x?: number;
  y?: number;
}

// ---------------------------------------------------------------------------
// Category → hex colour (for canvas rendering)
// ---------------------------------------------------------------------------

const CATEGORY_HEX: Record<string, string> = {
  Music: '#a855f7',     // purple-500
  Fitness: '#22c55e',   // green-500
  Journal: '#3b82f6',   // blue-500
  Ideas: '#6366f1',     // indigo-500
  Spiritual: '#f59e0b', // amber-500
  Learning: '#06b6d4',  // cyan-500
};

function categoryToHex(category: string): string {
  return CATEGORY_HEX[category] ?? '#94a3b8'; // slate-400 fallback
}

// ---------------------------------------------------------------------------
// BrainViewPage
// ---------------------------------------------------------------------------

/**
 * BrainViewPage — force-directed graph of notes and their semantic links.
 *
 * Uses react-force-graph-2d to render /api/insights/graph data.
 * Clicking a node navigates to NoteDetailPage.
 * Nodes are coloured by category. Max 200 nodes (enforced by backend).
 *
 * US-6 Task 5.2.
 */
export default function BrainViewPage(): React.ReactElement {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 400, height: 600 });

  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Measure container
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setDimensions({ width: rect.width || 400, height: rect.height || 600 });
  }, []);

  // Fetch graph data
  useEffect(() => {
    void apiGet<GraphData>('/api/insights/graph')
      .then((data) => setGraphData(data))
      .catch((err: Error) => setError(err.message))
      .finally(() => setIsLoading(false));
  }, []);

  const handleNodeClick = useCallback(
    (node: FGNode) => {
      navigate(`/note/${node.id}`);
    },
    [navigate],
  );

  // Canvas node painting
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

      // Label
      ctx.font = `${fontSize}px sans-serif`;
      ctx.fillStyle = '#cbd5e1'; // slate-300
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
            {graphData.nodes.length} nodes · {graphData.links.length} links
          </span>
        )}
      </header>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 border-b border-slate-800 px-4 py-2">
        {Object.entries(CATEGORY_HEX).map(([cat, hex]) => (
          <div key={cat} className="flex items-center gap-1">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: hex }}
            />
            <span className="text-xs text-slate-400">{cat}</span>
          </div>
        ))}
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

        {!isLoading && !error && graphData.nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-sm text-slate-500">
              No notes yet. Capture some notes to see your brain map.
            </p>
          </div>
        )}

        {!isLoading && !error && graphData.nodes.length > 0 && (
          <ForceGraph2D
            width={dimensions.width}
            height={dimensions.height}
            graphData={graphData}
            nodeId="id"
            linkSource="source"
            linkTarget="target"
            nodeCanvasObject={paintNode as (node: object, ctx: CanvasRenderingContext2D, globalScale: number) => void}
            nodeCanvasObjectMode={() => 'replace'}
            linkColor={() => '#334155'}
            linkWidth={(link) => {
              const l = link as GraphLink;
              return Math.max(1, (l.score ?? 0) * 3);
            }}
            onNodeClick={(node) => handleNodeClick(node as FGNode)}
            backgroundColor="#0F172A"
            nodePointerAreaPaint={(node, color, ctx) => {
              const n = node as FGNode;
              ctx.fillStyle = color;
              ctx.beginPath();
              ctx.arc(n.x ?? 0, n.y ?? 0, 8, 0, 2 * Math.PI);
              ctx.fill();
            }}
          />
        )}
      </div>
    </div>
  );
}
