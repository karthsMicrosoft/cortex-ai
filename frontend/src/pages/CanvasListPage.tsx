import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout, Plus, Trash2 } from 'lucide-react';
import {
  createCanvas,
  deleteCanvas,
  listCanvases,
  type CanvasOut,
} from '../api/canvas';
import { useCanvasStore } from '../store/canvasStore';
import { formatRelativeTime } from '../utils/formatters';

// ---------------------------------------------------------------------------
// CanvasListPage — grid of canvases (Phase 7 / PR B)
// ---------------------------------------------------------------------------

export default function CanvasListPage(): React.ReactElement {
  const navigate = useNavigate();
  const canvases = useCanvasStore((s) => s.canvases);
  const isLoading = useCanvasStore((s) => s.isLoading);
  const error = useCanvasStore((s) => s.error);
  const loadCanvases = useCanvasStore((s) => s.loadCanvases);
  const addCanvas = useCanvasStore((s) => s.addCanvas);
  const removeCanvas = useCanvasStore((s) => s.removeCanvas);
  const setLoading = useCanvasStore((s) => s.setLoading);
  const setError = useCanvasStore((s) => s.setError);
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listCanvases()
      .then((res) => {
        if (!cancelled) loadCanvases(res.items);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load canvases');
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [loadCanvases, setError, setLoading]);

  const handleCreate = useCallback(async () => {
    setIsCreating(true);
    try {
      const canvas = await createCanvas({});
      addCanvas(canvas);
      navigate(`/canvas/${canvas.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create canvas');
    } finally {
      setIsCreating(false);
    }
  }, [addCanvas, navigate, setError]);

  const handleDelete = useCallback(
    async (canvas: CanvasOut, e: React.MouseEvent) => {
      e.stopPropagation();
      if (!window.confirm(`Delete "${canvas.title}"? This cannot be undone.`)) return;
      try {
        await deleteCanvas(canvas.id);
        removeCanvas(canvas.id);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to delete canvas');
      }
    },
    [removeCanvas, setError],
  );

  const handleOpen = useCallback(
    (id: string) => {
      navigate(`/canvas/${id}`);
    },
    [navigate],
  );

  return (
    <div className="flex min-h-screen flex-col bg-[#0F172A] pb-24 text-slate-200">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
        <h1 className="flex items-center gap-2 text-lg font-semibold text-slate-100">
          <Layout className="h-5 w-5 text-indigo-400" aria-hidden="true" />
          Canvases
        </h1>
        <button
          type="button"
          onClick={() => void handleCreate()}
          disabled={isCreating}
          className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          data-testid="canvas-new-button"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {isCreating ? 'Creating…' : 'New Canvas'}
        </button>
      </header>

      {error && (
        <div
          role="alert"
          className="border-b border-red-700/40 bg-red-900/30 px-4 py-2 text-xs text-red-300"
        >
          {error}
        </div>
      )}

      <main className="flex flex-1 flex-col px-4 py-4">
        {isLoading ? (
          <div
            role="status"
            aria-label="Loading canvases"
            className="flex flex-1 items-center justify-center text-sm text-slate-500"
          >
            Loading canvases…
          </div>
        ) : canvases.length === 0 ? (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-sm text-slate-500">
              No canvases yet. Create one to start thinking visually.
            </p>
          </div>
        ) : (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {canvases.map((canvas) => (
              <li key={canvas.id}>
                <button
                  type="button"
                  onClick={() => handleOpen(canvas.id)}
                  className="group relative flex w-full flex-col gap-2 rounded-lg border border-slate-700 bg-slate-800 p-4 text-left transition-colors hover:border-indigo-500 hover:bg-slate-800/80 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  data-testid={`canvas-card-${canvas.id}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <h2 className="text-base font-semibold text-slate-100 line-clamp-1">
                      {canvas.title || 'Untitled canvas'}
                    </h2>
                    <span
                      className="shrink-0 rounded-full bg-indigo-900/40 px-2 py-0.5 text-[10px] font-medium text-indigo-300"
                      data-testid={`canvas-item-count-${canvas.id}`}
                    >
                      {canvas.item_count} item{canvas.item_count === 1 ? '' : 's'}
                    </span>
                  </div>
                  {canvas.description && (
                    <p className="line-clamp-2 text-xs text-slate-400">{canvas.description}</p>
                  )}
                  <div className="mt-auto flex items-center justify-between pt-2">
                    <span
                      className="text-[11px] text-slate-500"
                      data-testid={`canvas-updated-${canvas.id}`}
                    >
                      Updated {formatRelativeTime(canvas.updated_at)}
                    </span>
                    <span
                      role="button"
                      tabIndex={0}
                      aria-label={`Delete ${canvas.title}`}
                      onClick={(e) => void handleDelete(canvas, e)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          void handleDelete(canvas, e as unknown as React.MouseEvent);
                        }
                      }}
                      className="rounded p-1 text-slate-500 opacity-0 transition-opacity hover:bg-slate-700 hover:text-red-300 focus:opacity-100 group-hover:opacity-100"
                      data-testid={`canvas-delete-${canvas.id}`}
                    >
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
