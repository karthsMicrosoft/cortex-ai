import { useCallback, useEffect, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { Layout, Plus, X, Check, AlertCircle, Loader2 } from 'lucide-react';
import {
  addCanvasItem,
  createCanvas,
  listCanvases,
  type CanvasOut,
} from '../api/canvas';
import { ApiError } from '../api/client';

// ---------------------------------------------------------------------------
// AddToCanvasModal — canvas picker for adding a note to a canvas (PR C).
// ---------------------------------------------------------------------------

export interface AddToCanvasModalProps {
  noteId: string;
  noteTitle?: string;
  isOpen: boolean;
  onClose: () => void;
  onAdded?: (canvasId: string) => void;
}

type Status =
  | { kind: 'idle' }
  | { kind: 'adding'; canvasId: string }
  | { kind: 'success'; canvas: CanvasOut }
  | { kind: 'error'; message: string };

export function AddToCanvasModal({
  noteId,
  noteTitle,
  isOpen,
  onClose,
  onAdded,
}: AddToCanvasModalProps): React.ReactElement | null {
  const [canvases, setCanvases] = useState<CanvasOut[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>({ kind: 'idle' });
  const [isCreating, setIsCreating] = useState(false);

  // --- Reset state and fetch canvases when opened ---
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setStatus({ kind: 'idle' });
    setLoadError(null);
    setIsLoading(true);
    listCanvases()
      .then((res) => {
        if (!cancelled) setCanvases(res.items);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : 'Failed to load canvases');
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const handleAdd = useCallback(
    async (canvas: CanvasOut) => {
      setStatus({ kind: 'adding', canvasId: canvas.id });
      try {
        await addCanvasItem(canvas.id, {
          note_id: noteId,
          item_type: 'note',
          position_x: 100,
          position_y: 100,
        });
        setStatus({ kind: 'success', canvas });
        onAdded?.(canvas.id);
      } catch (err: unknown) {
        let message = 'Failed to add note to canvas';
        if (err instanceof ApiError) {
          if (err.status === 409 || /already/i.test(err.detail)) {
            message = 'Note is already on this canvas';
          } else {
            message = err.detail || message;
          }
        } else if (err instanceof Error) {
          message = err.message;
        }
        setStatus({ kind: 'error', message });
      }
    },
    [noteId, onAdded],
  );

  const handleCreateAndAdd = useCallback(async () => {
    setIsCreating(true);
    setStatus({ kind: 'idle' });
    try {
      const title = noteTitle ? `Canvas: ${noteTitle}` : undefined;
      const canvas = await createCanvas(title ? { title } : {});
      setCanvases((prev) => [canvas, ...prev]);
      await handleAdd(canvas);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to create canvas';
      setStatus({ kind: 'error', message });
    } finally {
      setIsCreating(false);
    }
  }, [handleAdd, noteTitle]);

  if (!isOpen) return null;

  return (
    <div
      data-testid="add-to-canvas-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-800 shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Add to canvas"
        aria-modal="true"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <Layout className="h-4 w-4 text-indigo-400" aria-hidden="true" />
            Add to Canvas
          </h2>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-700 hover:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Status banners */}
        {status.kind === 'success' && (
          <div
            data-testid="add-to-canvas-success"
            className="flex items-center gap-2 border-b border-emerald-700 bg-emerald-900/30 px-4 py-2 text-xs text-emerald-200"
          >
            <Check className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Added to {status.canvas.title}</span>
            <RouterLink
              to={`/canvas/${status.canvas.id}`}
              className="ml-auto text-emerald-300 underline hover:text-emerald-100"
            >
              Open
            </RouterLink>
          </div>
        )}
        {status.kind === 'error' && (
          <div
            data-testid="add-to-canvas-error"
            role="alert"
            className="flex items-center gap-2 border-b border-red-700 bg-red-900/30 px-4 py-2 text-xs text-red-200"
          >
            <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{status.message}</span>
          </div>
        )}

        {/* Body */}
        <div className="max-h-[60vh] overflow-y-auto px-2 py-2">
          {isLoading && (
            <div
              data-testid="add-to-canvas-loading"
              className="flex items-center justify-center gap-2 px-2 py-8 text-sm text-slate-400"
            >
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Loading canvases…
            </div>
          )}

          {!isLoading && loadError && (
            <p className="px-2 py-6 text-sm text-red-400">{loadError}</p>
          )}

          {!isLoading && !loadError && canvases.length === 0 && (
            <p
              data-testid="add-to-canvas-empty"
              className="px-2 py-6 text-center text-sm text-slate-400"
            >
              No canvases yet. Create your first one below.
            </p>
          )}

          {!isLoading && !loadError && canvases.length > 0 && (
            <ul className="flex flex-col gap-1">
              {canvases.map((c) => {
                const isAdding =
                  status.kind === 'adding' && status.canvasId === c.id;
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => void handleAdd(c)}
                      disabled={status.kind === 'adding'}
                      data-testid={`canvas-row-${c.id}`}
                      className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-700 focus:bg-slate-700 focus:outline-none disabled:opacity-50"
                    >
                      <span className="flex items-center gap-2 truncate">
                        <Layout
                          className="h-3.5 w-3.5 shrink-0 text-indigo-400"
                          aria-hidden="true"
                        />
                        <span className="truncate">{c.title}</span>
                      </span>
                      <span className="flex shrink-0 items-center gap-2 text-xs text-slate-500">
                        <span>{c.item_count} items</span>
                        {isAdding && (
                          <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                        )}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-slate-700 px-2 py-2">
          <button
            type="button"
            onClick={() => void handleCreateAndAdd()}
            disabled={isCreating || status.kind === 'adding'}
            data-testid="add-to-canvas-create-new"
            className="flex w-full items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:opacity-50"
          >
            {isCreating ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Plus className="h-4 w-4" aria-hidden="true" />
            )}
            Create New Canvas
          </button>
        </div>
      </div>
    </div>
  );
}

export default AddToCanvasModal;
