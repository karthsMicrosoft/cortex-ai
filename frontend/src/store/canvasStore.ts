import { create } from 'zustand';
import type { CanvasOut } from '../api/canvas';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CanvasState {
  canvases: CanvasOut[];
  isLoading: boolean;
  error: string | null;

  loadCanvases: (canvases: CanvasOut[]) => void;
  addCanvas: (canvas: CanvasOut) => void;
  updateCanvas: (id: string, patch: Partial<CanvasOut>) => void;
  removeCanvas: (id: string) => void;
  setLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useCanvasStore = create<CanvasState>()((set) => ({
  canvases: [],
  isLoading: false,
  error: null,

  loadCanvases: (canvases) => set({ canvases, isLoading: false, error: null }),

  addCanvas: (canvas) =>
    set((state) => ({
      canvases: [canvas, ...state.canvases],
    })),

  updateCanvas: (id, patch) =>
    set((state) => ({
      canvases: state.canvases.map((c) => (c.id === id ? { ...c, ...patch } : c)),
    })),

  removeCanvas: (id) =>
    set((state) => ({
      canvases: state.canvases.filter((c) => c.id !== id),
    })),

  setLoading: (isLoading) => set({ isLoading }),

  setError: (error) => set({ error }),
}));
