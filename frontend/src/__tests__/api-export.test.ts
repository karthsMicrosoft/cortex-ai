/**
 * api-export.test.ts — Round 15 / PR #23 (TDD red phase)
 *
 * Tests for frontend/src/api/export.ts — the downloadExport() helper that
 * pulls /api/export and triggers a browser download with a dated filename.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mock authStore so the helper picks up an access token
// ---------------------------------------------------------------------------

vi.mock('../store/authStore', () => {
  const state = { accessToken: 'test-token', user: { id: 'u1' } };
  const store = Object.assign(
    (selector: (s: typeof state) => unknown) => selector(state),
    { getState: () => state, subscribe: () => () => {}, setState: () => {} },
  );
  return { useAuthStore: store };
});

// ---------------------------------------------------------------------------
// fetch + URL + anchor stubs
// ---------------------------------------------------------------------------

const fetchMock = vi.fn();
const createObjectURL = vi.fn(() => 'blob:mock-url');
const revokeObjectURL = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();

  vi.stubGlobal('fetch', fetchMock);
  // jsdom doesn't implement URL.createObjectURL by default
  Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true });
  Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function mockJsonResponse(body: unknown, ok = true): Response {
  const blob = new Blob([JSON.stringify(body)], { type: 'application/json' });
  return {
    ok,
    status: ok ? 200 : 500,
    statusText: ok ? 'OK' : 'Internal Server Error',
    blob: () => Promise.resolve(blob),
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
    headers: new Headers({ 'content-type': 'application/json' }),
  } as unknown as Response;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('downloadExport (api/export.ts)', () => {
  it('downloadExport calls /api/export with auth header', async () => {
    fetchMock.mockResolvedValueOnce(mockJsonResponse({ exported_at: 'x', notes: [], summaries: [] }));

    const { downloadExport } = await import('../api/export');
    await downloadExport();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/api\/export$/);
    const headers = init.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer test-token');
  });

  it('downloadExport creates anchor with cortex-export-YYYY-MM-DD.json filename', async () => {
    fetchMock.mockResolvedValueOnce(mockJsonResponse({ exported_at: 'x', notes: [] }));

    const clickSpy = vi.fn();
    const origCreateElement = document.createElement.bind(document);
    const createElementSpy = vi
      .spyOn(document, 'createElement')
      .mockImplementation((tag: string) => {
        const el = origCreateElement(tag);
        if (tag === 'a') {
          (el as HTMLAnchorElement).click = clickSpy;
        }
        return el;
      });

    const { downloadExport } = await import('../api/export');
    await downloadExport();

    // Find the anchor that was created by the helper
    const anchorCalls = createElementSpy.mock.results
      .map((r) => r.value as HTMLElement)
      .filter((el) => el instanceof HTMLAnchorElement) as HTMLAnchorElement[];
    expect(anchorCalls.length).toBeGreaterThan(0);

    const downloaded = anchorCalls.find((a) => a.download && a.download.startsWith('cortex-export-'));
    expect(downloaded, 'expected an anchor with a cortex-export-* download attribute').toBeTruthy();
    expect(downloaded!.download).toMatch(/^cortex-export-\d{4}-\d{2}-\d{2}\.json$/);
    expect(clickSpy).toHaveBeenCalled();

    createElementSpy.mockRestore();
  });

  it('downloadExport revokes object URL after click', async () => {
    fetchMock.mockResolvedValueOnce(mockJsonResponse({ exported_at: 'x', notes: [] }));

    const { downloadExport } = await import('../api/export');
    await downloadExport();

    expect(createObjectURL).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock-url');
  });

  it('downloadExport throws on non-ok response', async () => {
    fetchMock.mockResolvedValueOnce(mockJsonResponse({ detail: 'boom' }, false));

    const { downloadExport } = await import('../api/export');
    await expect(downloadExport()).rejects.toThrow();
  });
});
