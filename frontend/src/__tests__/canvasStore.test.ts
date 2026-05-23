/**
 * canvasStore.test.ts — Phase 7 PR B
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useCanvasStore } from '../store/canvasStore';
import type { CanvasOut } from '../api/canvas';

const C1: CanvasOut = {
  id: 'c1',
  title: 'A',
  description: null,
  viewport_x: 0,
  viewport_y: 0,
  viewport_zoom: 1,
  item_count: 0,
  created_at: '2026-04-10T09:00:00Z',
  updated_at: '2026-04-10T09:00:00Z',
};
const C2: CanvasOut = { ...C1, id: 'c2', title: 'B' };

beforeEach(() => {
  useCanvasStore.setState({ canvases: [], isLoading: false, error: null });
});

describe('canvasStore', () => {
  it('loads canvases', () => {
    useCanvasStore.getState().loadCanvases([C1, C2]);
    expect(useCanvasStore.getState().canvases).toHaveLength(2);
    expect(useCanvasStore.getState().isLoading).toBe(false);
    expect(useCanvasStore.getState().error).toBeNull();
  });

  it('adds a canvas to the front of the list', () => {
    useCanvasStore.getState().loadCanvases([C1]);
    useCanvasStore.getState().addCanvas(C2);
    expect(useCanvasStore.getState().canvases[0].id).toBe('c2');
  });

  it('updates an existing canvas by id', () => {
    useCanvasStore.getState().loadCanvases([C1]);
    useCanvasStore.getState().updateCanvas('c1', { title: 'Renamed' });
    expect(useCanvasStore.getState().canvases[0].title).toBe('Renamed');
  });

  it('removes a canvas by id', () => {
    useCanvasStore.getState().loadCanvases([C1, C2]);
    useCanvasStore.getState().removeCanvas('c1');
    expect(useCanvasStore.getState().canvases).toHaveLength(1);
    expect(useCanvasStore.getState().canvases[0].id).toBe('c2');
  });

  it('toggles loading and error flags', () => {
    useCanvasStore.getState().setLoading(true);
    expect(useCanvasStore.getState().isLoading).toBe(true);
    useCanvasStore.getState().setError('oops');
    expect(useCanvasStore.getState().error).toBe('oops');
  });
});
