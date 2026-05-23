import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  Handle,
  Position,
  ReactFlowProvider,
  useReactFlow,
  type Node,
  type Edge,
  type Connection,
  type NodeProps,
  type NodeChange,
  type EdgeChange,
  type Viewport,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { ArrowLeft, LayoutGrid, Plus, Type as TypeIcon } from 'lucide-react';
import {
  addCanvasEdge,
  addCanvasItem,
  autoLayoutCanvas,
  deleteCanvasEdge,
  deleteCanvasItem,
  getCanvas,
  updateCanvas,
  updateCanvasItem,
  type CanvasDetailOut,
  type CanvasEdgeOut,
  type CanvasItemOut,
} from '../api/canvas';
import { useCanvasUndoRedo, type MoveCommand } from '../hooks/useCanvasUndoRedo';

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

// ---------------------------------------------------------------------------
// Zoom context — NoteCardNode reads zoom for LOD (title-only at low zoom).
// ---------------------------------------------------------------------------

const ZoomContext = createContext(1);

// ---------------------------------------------------------------------------
// Helpers — backend ↔ reactflow conversion
// ---------------------------------------------------------------------------

interface NodeData {
  label: string | null;
  noteId: string | null;
  noteTitle: string | null;
  noteSummary: string | null;
  noteContent: string | null;
  lastKnownTitle: string | null;
  color: string | null;
  itemType: CanvasItemOut['item_type'];
  version: number;
  width: number | null;
  height: number | null;
  zoom?: number;
  onNoteOpen?: (noteId: string) => void;
  [key: string]: unknown;
}

function itemToNode(item: CanvasItemOut): Node<NodeData> {
  return {
    id: item.id,
    type: item.item_type === 'note' ? 'noteCard' : item.item_type,
    position: { x: item.position_x, y: item.position_y },
    data: {
      label: item.label,
      noteId: item.note_id,
      noteTitle: item.note_title,
      noteSummary: item.note_summary,
      noteContent: item.note_content,
      lastKnownTitle: item.last_known_title,
      color: item.color,
      itemType: item.item_type,
      version: item.version,
      width: item.width,
      height: item.height,
    },
    style: item.width && item.height ? { width: item.width, height: item.height } : undefined,
  };
}

function edgeToFlow(edge: CanvasEdgeOut): Edge {
  return {
    id: edge.id,
    source: edge.source_item_id,
    target: edge.target_item_id,
    label: edge.label ?? undefined,
    style:
      edge.style === 'dashed'
        ? { strokeDasharray: '5,5' }
        : edge.style === 'bold'
          ? { strokeWidth: 3 }
          : undefined,
    type: 'default',
  };
}

// ---------------------------------------------------------------------------
// Custom Node components
// ---------------------------------------------------------------------------

function NoteCardNode({ data }: NodeProps<Node<NodeData>>): React.ReactElement {
  const zoom = useContext(ZoomContext);
  const isGhost = data.noteId === null;
  const title = data.noteTitle ?? data.lastKnownTitle ?? 'Untitled note';
  const summary = data.noteSummary ?? '';
  const showSummary = zoom >= 0.5;

  const handleClick = () => {
    if (!isGhost && data.noteId && data.onNoteOpen) {
      data.onNoteOpen(data.noteId);
    }
  };

  return (
    <div
      data-testid={`note-card-node-${isGhost ? 'ghost' : 'active'}`}
      data-ghost={isGhost ? 'true' : 'false'}
      onClick={handleClick}
      className={[
        'w-56 rounded-md border bg-slate-800 p-3 text-xs text-slate-200 shadow-sm transition',
        isGhost
          ? 'border-dashed border-slate-600 opacity-60'
          : 'border-slate-700 hover:border-indigo-500 cursor-pointer',
      ].join(' ')}
    >
      <Handle type="target" position={Position.Top} />
      <h3 className="line-clamp-1 text-sm font-semibold text-slate-100">{title}</h3>
      {showSummary && summary && (
        <p className="mt-1 line-clamp-2 text-[11px] text-slate-400">{summary}</p>
      )}
      {isGhost && (
        <span className="mt-1 inline-block text-[10px] uppercase tracking-wide text-amber-400">
          Deleted note
        </span>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

function GroupNode({ data }: NodeProps<Node<NodeData>>): React.ReactElement {
  const bg = data.color ?? '#1e293b';
  return (
    <div
      data-testid="group-node"
      className="flex h-full w-full items-center justify-center rounded-lg border-2 border-dashed border-slate-500 p-4 text-sm font-semibold text-slate-100"
      style={{ backgroundColor: bg, minWidth: 160, minHeight: 100 }}
    >
      <Handle type="target" position={Position.Top} />
      <span className="line-clamp-2 text-center">{data.label ?? 'Group'}</span>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

function TextNode({ data, id }: NodeProps<Node<NodeData>>): React.ReactElement {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(data.label ?? 'Text');
  useEffect(() => {
    setValue(data.label ?? 'Text');
  }, [data.label]);
  return (
    <div
      data-testid="text-node"
      data-node-id={id}
      onDoubleClick={() => setEditing(true)}
      className="min-w-[120px] rounded border border-slate-600 bg-slate-900/80 px-3 py-2 text-xs text-slate-200"
    >
      <Handle type="target" position={Position.Top} />
      {editing ? (
        <input
          type="text"
          value={value}
          autoFocus
          onChange={(e) => setValue(e.target.value)}
          onBlur={() => setEditing(false)}
          className="w-full bg-transparent text-xs text-slate-100 outline-none"
        />
      ) : (
        <span>{value}</span>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const NODE_TYPES = {
  noteCard: NoteCardNode,
  group: GroupNode,
  text: TextNode,
};

// ---------------------------------------------------------------------------
// CanvasEditorPage
// ---------------------------------------------------------------------------

function CanvasEditorInner(): React.ReactElement {
  const { id: canvasId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const reactFlowInstance = useReactFlow();
  const [canvas, setCanvas] = useState<CanvasDetailOut | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');
  const [currentZoom, setCurrentZoom] = useState(1);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<NodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');

  // itemId -> current version (for optimistic concurrency)
  const versionsRef = useRef<Map<string, number>>(new Map());
  const dragDebounceRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  // itemId -> position before the current drag (for undo command building)
  const dragStartPosRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const viewportRef = useRef<Viewport>({ x: 0, y: 0, zoom: 1 });
  const inFlightSavesRef = useRef(0);
  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const undoRedo = useCanvasUndoRedo();
  // Tracks moves that originated from undo/redo so we don't re-push them on
  // the resulting drag-end event.
  const suppressNextPushRef = useRef<Set<string>>(new Set());

  const markSaving = useCallback(() => {
    inFlightSavesRef.current += 1;
    setSaveStatus('saving');
    if (savedTimerRef.current) {
      clearTimeout(savedTimerRef.current);
      savedTimerRef.current = null;
    }
  }, []);

  const markSaved = useCallback(() => {
    inFlightSavesRef.current = Math.max(0, inFlightSavesRef.current - 1);
    if (inFlightSavesRef.current === 0) {
      setSaveStatus('saved');
      if (savedTimerRef.current) clearTimeout(savedTimerRef.current);
      savedTimerRef.current = setTimeout(() => setSaveStatus('idle'), 2000);
    }
  }, []);

  const markError = useCallback(() => {
    inFlightSavesRef.current = Math.max(0, inFlightSavesRef.current - 1);
    setSaveStatus('error');
  }, []);

  const handleNoteOpen = useCallback(
    (noteId: string) => {
      navigate(`/note/${noteId}`);
    },
    [navigate],
  );

  // Initial load
  useEffect(() => {
    if (!canvasId) return;
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    setNotFound(false);
    getCanvas(canvasId)
      .then((data) => {
        if (cancelled) return;
        setCanvas(data);
        setTitleDraft(data.title);
        const flowNodes = data.items.map((item) => {
          const n = itemToNode(item);
          versionsRef.current.set(item.id, item.version);
          return {
            ...n,
            data: { ...n.data, onNoteOpen: handleNoteOpen },
          };
        });
        setNodes(flowNodes);
        setEdges(data.edges.map(edgeToFlow));
        // Restore saved viewport if non-default
        if (data.viewport_x !== 0 || data.viewport_y !== 0 || data.viewport_zoom !== 1) {
          viewportRef.current = { x: data.viewport_x, y: data.viewport_y, zoom: data.viewport_zoom };
          setCurrentZoom(data.viewport_zoom);
          setTimeout(() => {
            reactFlowInstance.setViewport({
              x: data.viewport_x,
              y: data.viewport_y,
              zoom: data.viewport_zoom,
            });
          }, 50);
        }
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const status = (err as { status?: number }).status;
        if (status === 404) setNotFound(true);
        else setError(err instanceof Error ? err.message : 'Failed to load canvas');
        setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [canvasId, setNodes, setEdges, handleNoteOpen]);

  // Save viewport on unmount (best-effort)
  useEffect(() => {
    const cid = canvasId;
    return () => {
      const timeouts = dragDebounceRef.current;
      timeouts.forEach((t) => clearTimeout(t));
      timeouts.clear();
      if (cid) {
        const vp = viewportRef.current;
        void updateCanvas(cid, {
          viewport_x: vp.x,
          viewport_y: vp.y,
          viewport_zoom: vp.zoom,
        })?.catch(() => { /* best-effort */ });
      }
    };
  }, [canvasId]);

  const persistItemPosition = useCallback(
    (itemId: string, x: number, y: number) => {
      if (!canvasId) return;
      const existing = dragDebounceRef.current.get(itemId);
      if (existing) clearTimeout(existing);
      markSaving();
      const t = setTimeout(async () => {
        const version = versionsRef.current.get(itemId) ?? 1;
        try {
          const updated = await updateCanvasItem(canvasId, itemId, {
            position_x: x,
            position_y: y,
            version,
          });
          versionsRef.current.set(itemId, updated.version);
          markSaved();
        } catch (err: unknown) {
          const status = (err as { status?: number }).status;
          if (status === 409 && canvasId) {
            // Conflict — re-fetch canvas
            try {
              const fresh = await getCanvas(canvasId);
              setCanvas(fresh);
              const flowNodes = fresh.items.map((item) => {
                const n = itemToNode(item);
                versionsRef.current.set(item.id, item.version);
                return { ...n, data: { ...n.data, onNoteOpen: handleNoteOpen } };
              });
              setNodes(flowNodes);
              setEdges(fresh.edges.map(edgeToFlow));
              markSaved();
            } catch {
              markError();
            }
          } else {
            markError();
          }
        }
      }, 400);
      dragDebounceRef.current.set(itemId, t);
    },
    [canvasId, setNodes, setEdges, handleNoteOpen, markSaving, markSaved, markError],
  );

  const handleNodesChange = useCallback(
    (changes: NodeChange<Node<NodeData>>[]) => {
      onNodesChange(changes);
      for (const change of changes) {
        if (change.type === 'position') {
          // Record drag-start position once, so we can build an undo command.
          if (change.dragging === true && !dragStartPosRef.current.has(change.id)) {
            const current = nodes.find((n) => n.id === change.id);
            if (current) {
              dragStartPosRef.current.set(change.id, { ...current.position });
            }
          }
          if (change.position && change.dragging === false) {
            const start = dragStartPosRef.current.get(change.id);
            dragStartPosRef.current.delete(change.id);
            if (suppressNextPushRef.current.has(change.id)) {
              suppressNextPushRef.current.delete(change.id);
            } else if (start && (start.x !== change.position.x || start.y !== change.position.y)) {
              undoRedo.push({
                type: 'move',
                itemId: change.id,
                fromX: start.x,
                fromY: start.y,
                toX: change.position.x,
                toY: change.position.y,
              });
            }
            persistItemPosition(change.id, change.position.x, change.position.y);
          }
        }
      }
    },
    [onNodesChange, persistItemPosition, nodes, undoRedo],
  );

  // Apply a move command to local nodes + persist it. Used by undo/redo.
  const applyMove = useCallback(
    (cmd: MoveCommand) => {
      suppressNextPushRef.current.add(cmd.itemId);
      setNodes((ns) =>
        ns.map((n) =>
          n.id === cmd.itemId ? { ...n, position: { x: cmd.toX, y: cmd.toY } } : n,
        ),
      );
      persistItemPosition(cmd.itemId, cmd.toX, cmd.toY);
    },
    [setNodes, persistItemPosition],
  );

  const handleUndo = useCallback(() => {
    const cmd = undoRedo.undo();
    if (cmd) applyMove(cmd);
  }, [undoRedo, applyMove]);

  const handleRedo = useCallback(() => {
    const cmd = undoRedo.redo();
    if (cmd) applyMove(cmd);
  }, [undoRedo, applyMove]);

  const handleEdgesChange = useCallback(
    (changes: EdgeChange<Edge>[]) => {
      onEdgesChange(changes);
      if (!canvasId) return;
      for (const change of changes) {
        if (change.type === 'remove') {
          void deleteCanvasEdge(canvasId, change.id).catch(() => {
            /* ignore */
          });
        }
      }
    },
    [canvasId, onEdgesChange],
  );

  const handleConnect = useCallback(
    async (connection: Connection) => {
      if (!canvasId || !connection.source || !connection.target) return;
      try {
        const created = await addCanvasEdge(canvasId, {
          source_item_id: connection.source,
          target_item_id: connection.target,
        });
        setEdges((es) => addEdge(edgeToFlow(created), es));
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to add edge');
      }
    },
    [canvasId, setEdges],
  );

  const handleNodesDelete = useCallback(
    (deleted: Node[]) => {
      if (!canvasId) return;
      for (const node of deleted) {
        void deleteCanvasItem(canvasId, node.id).catch(() => {
          /* ignore */
        });
        versionsRef.current.delete(node.id);
      }
    },
    [canvasId],
  );

  const handleAddGroup = useCallback(async () => {
    if (!canvasId) return;
    try {
      const item = await addCanvasItem(canvasId, {
        item_type: 'group',
        position_x: 100,
        position_y: 100,
        width: 240,
        height: 160,
        color: '#312e81',
        label: 'Group',
      });
      const node = itemToNode(item);
      versionsRef.current.set(item.id, item.version);
      setNodes((ns) => [...ns, { ...node, data: { ...node.data, onNoteOpen: handleNoteOpen } }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add group');
    }
  }, [canvasId, setNodes, handleNoteOpen]);

  const handleAddText = useCallback(async () => {
    if (!canvasId) return;
    try {
      const item = await addCanvasItem(canvasId, {
        item_type: 'text',
        position_x: 200,
        position_y: 200,
        label: 'Text',
      });
      const node = itemToNode(item);
      versionsRef.current.set(item.id, item.version);
      setNodes((ns) => [...ns, { ...node, data: { ...node.data, onNoteOpen: handleNoteOpen } }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add text');
    }
  }, [canvasId, setNodes, handleNoteOpen]);

  const handleAutoLayout = useCallback(async () => {
    if (!canvasId) return;
    try {
      const items = await autoLayoutCanvas(canvasId);
      setNodes((current) => {
        const byId = new Map(items.map((it) => [it.id, it]));
        return current.map((n) => {
          const it = byId.get(n.id);
          if (!it) return n;
          versionsRef.current.set(it.id, it.version);
          return { ...n, position: { x: it.position_x, y: it.position_y } };
        });
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Auto-layout failed');
    }
  }, [canvasId, setNodes]);

  const handleSaveTitle = useCallback(async () => {
    if (!canvasId || !canvas || titleDraft === canvas.title) return;
    try {
      const updated = await updateCanvas(canvasId, { title: titleDraft });
      setCanvas((c) => (c ? { ...c, ...updated } : c));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update title');
    }
  }, [canvasId, canvas, titleDraft]);

  const nodeTypes = useMemo(() => NODE_TYPES, []);

  const handleViewportChange = useCallback((vp: Viewport) => {
    viewportRef.current = vp;
    setCurrentZoom(vp.zoom);
  }, []);

  // Keyboard shortcuts: Ctrl+Z undo, Ctrl+Shift+Z / Ctrl+Y redo, Escape deselect.
  useEffect(() => {
    const isEditable = (el: EventTarget | null): boolean => {
      if (!(el instanceof HTMLElement)) return false;
      const tag = el.tagName;
      return tag === 'INPUT' || tag === 'TEXTAREA' || el.isContentEditable;
    };
    const onKey = (e: KeyboardEvent) => {
      if (isEditable(e.target)) return;
      const ctrl = e.ctrlKey || e.metaKey;
      if (ctrl && !e.shiftKey && (e.key === 'z' || e.key === 'Z')) {
        e.preventDefault();
        handleUndo();
      } else if (ctrl && ((e.shiftKey && (e.key === 'z' || e.key === 'Z')) || e.key === 'y' || e.key === 'Y')) {
        e.preventDefault();
        handleRedo();
      } else if (e.key === 'Escape') {
        setNodes((ns) => ns.map((n) => (n.selected ? { ...n, selected: false } : n)));
        setEdges((es) => es.map((eg) => (eg.selected ? { ...eg, selected: false } : eg)));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [handleUndo, handleRedo, setNodes, setEdges]);

  // Cleanup saved-timer on unmount.
  useEffect(() => {
    return () => {
      if (savedTimerRef.current) clearTimeout(savedTimerRef.current);
    };
  }, []);

  const isEmpty = !isLoading && nodes.length === 0;

  if (notFound) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[#0F172A] pb-24 text-slate-200">
        <h1 className="text-2xl font-semibold text-slate-100">Canvas not found</h1>
        <p className="mt-2 text-sm text-slate-400">It may have been deleted.</p>
        <button
          type="button"
          onClick={() => navigate('/canvases')}
          className="mt-4 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500"
        >
          Back to canvases
        </button>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-[#0F172A] pb-16 text-slate-200">
      {/* Toolbar */}
      <header className="flex flex-wrap items-center gap-2 border-b border-slate-700 px-3 py-2">
        <button
          type="button"
          onClick={() => navigate('/canvases')}
          aria-label="Back to canvases"
          data-testid="canvas-back-button"
          className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <input
          type="text"
          value={titleDraft}
          onChange={(e) => setTitleDraft(e.target.value)}
          onBlur={() => void handleSaveTitle()}
          aria-label="Canvas title"
          data-testid="canvas-title-input"
          placeholder="Untitled canvas"
          className="flex-1 bg-transparent text-sm font-semibold text-slate-100 outline-none focus:underline"
        />
        <button
          type="button"
          onClick={() => void handleAddGroup()}
          data-testid="canvas-add-group"
          className="inline-flex items-center gap-1 rounded-md border border-slate-600 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-800"
        >
          <Plus className="h-3 w-3" /> Group
        </button>
        <button
          type="button"
          onClick={() => void handleAddText()}
          data-testid="canvas-add-text"
          className="inline-flex items-center gap-1 rounded-md border border-slate-600 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-800"
        >
          <TypeIcon className="h-3 w-3" /> Text
        </button>
        <button
          type="button"
          onClick={() => void handleAutoLayout()}
          data-testid="canvas-auto-layout"
          className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-indigo-500"
        >
          <LayoutGrid className="h-3 w-3" /> Auto-layout
        </button>
        <span
          data-testid="canvas-save-indicator"
          data-status={saveStatus}
          aria-live="polite"
          className={[
            'ml-1 min-w-[60px] text-right text-[10px] tabular-nums',
            saveStatus === 'error' ? 'text-red-400' : 'text-slate-400',
          ].join(' ')}
        >
          {saveStatus === 'saving' && 'Saving…'}
          {saveStatus === 'saved' && 'Saved ✓'}
          {saveStatus === 'error' && 'Save failed'}
        </span>
      </header>

      {error && (
        <div
          role="alert"
          className="border-b border-red-700/40 bg-red-900/30 px-4 py-2 text-xs text-red-300"
        >
          {error}
        </div>
      )}

      {isLoading ? (
        <div
          role="status"
          aria-label="Loading canvas"
          className="flex flex-1 items-center justify-center text-sm text-slate-500"
        >
          Loading canvas…
        </div>
      ) : (
        <div
          className="relative h-[calc(100vh-8rem)] w-full"
          data-testid="canvas-flow-wrapper"
          style={{ touchAction: 'none' }}
        >
          {isEmpty && (
            <div
              data-testid="canvas-empty-state"
              className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center px-6 text-center"
            >
              <p className="text-sm text-slate-300">
                This canvas is empty. Use the toolbar to add a group or text item,
                or open a note to add it here.
              </p>
              <p className="mt-2 text-[11px] text-slate-500">
                Shortcuts: Ctrl+Z undo · Ctrl+Shift+Z redo · Delete to remove · Esc to deselect
              </p>
            </div>
          )}
          <ZoomContext.Provider value={currentZoom}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
            onConnect={handleConnect}
            onNodesDelete={handleNodesDelete}
            onViewportChange={handleViewportChange}
            nodeTypes={nodeTypes}
            defaultViewport={{ x: 0, y: 0, zoom: 1 }}
            fitView={!canvas || (canvas.viewport_x === 0 && canvas.viewport_y === 0 && canvas.viewport_zoom === 1)}
          >
            <Background />
            <Controls />
            <MiniMap />
          </ReactFlow>
          </ZoomContext.Provider>
        </div>
      )}
    </div>
  );
}

export default function CanvasEditorPage(): React.ReactElement {
  return (
    <ReactFlowProvider>
      <CanvasEditorInner />
    </ReactFlowProvider>
  );
}
