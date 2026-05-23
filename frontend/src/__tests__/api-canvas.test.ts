/**
 * api-canvas.test.ts — Phase 7 PR B
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../store/authStore', () => ({
  useAuthStore: {
    getState: () => ({ accessToken: 'tok', setAccessToken: vi.fn(), logout: vi.fn() }),
  },
}));

import * as api from '../api/canvas';

function mockFetchOk(body: unknown = {}) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    headers: { get: () => null },
    json: async () => body,
  });
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe('canvas API client', () => {
  it('listCanvases issues GET /api/canvases', async () => {
    const f = mockFetchOk({ items: [], total: 0 });
    vi.stubGlobal('fetch', f);
    await api.listCanvases();
    const [url, init] = f.mock.calls[0];
    expect(url).toContain('/api/canvases');
    expect(init.method).toBe('GET');
  });

  it('createCanvas POSTs to /api/canvases', async () => {
    const f = mockFetchOk({ id: 'x' });
    vi.stubGlobal('fetch', f);
    await api.createCanvas({ title: 'T' });
    const [url, init] = f.mock.calls[0];
    expect(url).toContain('/api/canvases');
    expect(init.method).toBe('POST');
    expect(init.body).toContain('"title":"T"');
  });

  it('getCanvas GETs /api/canvases/:id', async () => {
    const f = mockFetchOk({ id: 'cv1' });
    vi.stubGlobal('fetch', f);
    await api.getCanvas('cv1');
    expect(f.mock.calls[0][0]).toContain('/api/canvases/cv1');
    expect(f.mock.calls[0][1].method).toBe('GET');
  });

  it('updateCanvas PATCHes /api/canvases/:id', async () => {
    const f = mockFetchOk({ id: 'cv1' });
    vi.stubGlobal('fetch', f);
    await api.updateCanvas('cv1', { title: 'New' });
    expect(f.mock.calls[0][0]).toContain('/api/canvases/cv1');
    expect(f.mock.calls[0][1].method).toBe('PATCH');
  });

  it('deleteCanvas DELETEs /api/canvases/:id', async () => {
    const f = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: { get: () => null },
      json: async () => ({}),
    });
    vi.stubGlobal('fetch', f);
    await api.deleteCanvas('cv1');
    expect(f.mock.calls[0][0]).toContain('/api/canvases/cv1');
    expect(f.mock.calls[0][1].method).toBe('DELETE');
  });

  it('addCanvasItem POSTs items', async () => {
    const f = mockFetchOk({ id: 'it1' });
    vi.stubGlobal('fetch', f);
    await api.addCanvasItem('cv1', { item_type: 'group', label: 'g' });
    expect(f.mock.calls[0][0]).toContain('/api/canvases/cv1/items');
    expect(f.mock.calls[0][1].method).toBe('POST');
  });

  it('updateCanvasItem PATCHes a single item with version', async () => {
    const f = mockFetchOk({ id: 'it1', version: 2 });
    vi.stubGlobal('fetch', f);
    await api.updateCanvasItem('cv1', 'it1', { position_x: 5, position_y: 6, version: 1 });
    expect(f.mock.calls[0][0]).toContain('/api/canvases/cv1/items/it1');
    expect(f.mock.calls[0][1].method).toBe('PATCH');
    expect(f.mock.calls[0][1].body).toContain('"version":1');
  });

  it('batchUpdateItems POSTs to /items/batch', async () => {
    const f = mockFetchOk([]);
    vi.stubGlobal('fetch', f);
    await api.batchUpdateItems('cv1', [{ id: 'i1', version: 1, position_x: 1, position_y: 1 }]);
    expect(f.mock.calls[0][0]).toContain('/api/canvases/cv1/items/batch');
    expect(f.mock.calls[0][1].method).toBe('POST');
  });

  it('deleteCanvasItem DELETEs single item', async () => {
    const f = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: { get: () => null },
      json: async () => ({}),
    });
    vi.stubGlobal('fetch', f);
    await api.deleteCanvasItem('cv1', 'it1');
    expect(f.mock.calls[0][0]).toContain('/api/canvases/cv1/items/it1');
    expect(f.mock.calls[0][1].method).toBe('DELETE');
  });

  it('addCanvasEdge POSTs to /edges', async () => {
    const f = mockFetchOk({ id: 'e1' });
    vi.stubGlobal('fetch', f);
    await api.addCanvasEdge('cv1', { source_item_id: 'a', target_item_id: 'b' });
    expect(f.mock.calls[0][0]).toContain('/api/canvases/cv1/edges');
    expect(f.mock.calls[0][1].method).toBe('POST');
  });

  it('deleteCanvasEdge DELETEs /edges/:id', async () => {
    const f = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: { get: () => null },
      json: async () => ({}),
    });
    vi.stubGlobal('fetch', f);
    await api.deleteCanvasEdge('cv1', 'e1');
    expect(f.mock.calls[0][0]).toContain('/api/canvases/cv1/edges/e1');
    expect(f.mock.calls[0][1].method).toBe('DELETE');
  });

  it('autoLayoutCanvas POSTs to /auto-layout', async () => {
    const f = mockFetchOk([]);
    vi.stubGlobal('fetch', f);
    await api.autoLayoutCanvas('cv1');
    expect(f.mock.calls[0][0]).toContain('/api/canvases/cv1/auto-layout');
    expect(f.mock.calls[0][1].method).toBe('POST');
  });
});
