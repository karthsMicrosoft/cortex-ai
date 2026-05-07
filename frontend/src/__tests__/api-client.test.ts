/**
 * Task 3.2 (API client fetch wrapper) — TDD red
 *
 * Tests that api/client.ts:
 *   - Exports ApiError class with `code`, `detail`, `status` properties
 *   - apiGet/apiPost/apiPut/apiDelete attach Authorization: Bearer header from authStore
 *   - On 401 response calls /api/auth/refresh and retries once
 *   - Throws ApiError with `code` and `detail` on non-2xx (after retry fails)
 *   - On success returns parsed JSON
 *
 * Public interface expected by tests:
 *   - export class ApiError extends Error { code: string; detail: string; status: number }
 *   - export async function apiGet<T>(url, options?): Promise<T>
 *   - export async function apiPost<T>(url, body?, options?): Promise<T>
 *   - export async function apiPut<T>(url, body?, options?): Promise<T>
 *   - export async function apiDelete(url, options?): Promise<void>
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// We mock authStore so the client can pull the token
vi.mock('../store/authStore', () => ({
  useAuthStore: {
    getState: vi.fn(() => ({
      accessToken: 'test-access-token',
      user: { id: 'u1', email: 'a@b.com', display_name: 'A' },
      login: vi.fn(),
      logout: vi.fn(),
      setAccessToken: vi.fn(),
    })),
  },
}));

import { apiGet, apiPost, apiPut, apiDelete, ApiError } from '../api/client';
import { useAuthStore } from '../store/authStore';

// ---------------------------------------------------------------------------
// Default mock state — restored before EVERY test so that one test's
// .mockReturnValue(...) override (e.g. the refresh-on-401 path which sets
// accessToken='old-token') doesn't leak into the next test. vi.clearAllMocks()
// only clears call history; it does NOT restore implementations.
// ---------------------------------------------------------------------------

const _DEFAULT_AUTH_STATE = {
  accessToken: 'test-access-token',
  user: { id: 'u1', email: 'a@b.com', display_name: 'A' },
  login: vi.fn(),
  logout: vi.fn(),
  setAccessToken: vi.fn(),
};

beforeEach(() => {
  vi.mocked(useAuthStore.getState).mockReturnValue({ ..._DEFAULT_AUTH_STATE });
});

// ---------------------------------------------------------------------------
// fetch mock helpers
// ---------------------------------------------------------------------------

function makeFetchMock(
  responses: Array<{ status: number; body: unknown; headers?: Record<string, string> }>
) {
  let callIndex = 0;
  return vi.fn(async (_url: string, _init?: RequestInit) => {
    const resp = responses[Math.min(callIndex, responses.length - 1)];
    callIndex++;
    const bodyText = JSON.stringify(resp.body);
    return {
      ok: resp.status >= 200 && resp.status < 300,
      status: resp.status,
      statusText: resp.status === 200 ? 'OK' : 'Error',
      headers: {
        get: (name: string) => resp.headers?.[name.toLowerCase()] ?? null,
      },
      json: async () => JSON.parse(bodyText),
    } as unknown as Response;
  });
}

describe('ApiError class', () => {
  it('is exported from api/client', () => {
    expect(ApiError).toBeDefined();
  });

  it('extends Error', () => {
    const err = new ApiError(404, 'not_found', 'Note not found');
    expect(err).toBeInstanceOf(Error);
    expect(err).toBeInstanceOf(ApiError);
  });

  it('has status, code, and detail properties', () => {
    const err = new ApiError(422, 'validation_error', 'Bad input');
    expect(err.status).toBe(422);
    expect(err.code).toBe('validation_error');
    expect(err.detail).toBe('Bad input');
  });
});

describe('apiGet — fetch wrapper (Task 3.2)', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.clearAllMocks();
  });

  // ----------- Authorization header -----------

  it('attaches Authorization: Bearer header from authStore', async () => {
    const mockFetch = makeFetchMock([{ status: 200, body: { data: 'ok' } }]);
    globalThis.fetch = mockFetch;

    await apiGet('/api/notes');

    const [_url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const headers = init?.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer test-access-token');
  });

  it('sends correct URL', async () => {
    const mockFetch = makeFetchMock([{ status: 200, body: {} }]);
    globalThis.fetch = mockFetch;

    await apiGet('/api/notes');

    const [url] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/notes');
  });

  it('returns parsed JSON on success', async () => {
    const responseBody = { items: [{ id: '1', content: 'hello' }] };
    globalThis.fetch = makeFetchMock([{ status: 200, body: responseBody }]);

    const result = await apiGet('/api/notes');
    expect(result).toEqual(responseBody);
  });

  // ----------- 401 refresh + retry -----------

  it('calls /api/auth/refresh on 401 and retries the original request', async () => {
    const mockFetch = makeFetchMock([
      { status: 401, body: { detail: 'Unauthorized', code: 'token_expired' } },
      { status: 200, body: { access_token: 'new-token' } }, // refresh response
      { status: 200, body: { items: [] } },                 // retry response
    ]);
    globalThis.fetch = mockFetch;

    const result = await apiGet('/api/notes');

    expect(mockFetch).toHaveBeenCalledTimes(3);
    // Second call must be to the refresh endpoint
    const [refreshUrl] = mockFetch.mock.calls[1] as [string, RequestInit];
    expect(refreshUrl).toBe('/api/auth/refresh');
    expect(result).toEqual({ items: [] });
  });

  it('calls setAccessToken with the new token after refresh', async () => {
    const mockSetAccessToken = vi.fn();
    vi.mocked(useAuthStore.getState).mockReturnValue({
      accessToken: 'old-token',
      user: null,
      login: vi.fn(),
      logout: vi.fn(),
      setAccessToken: mockSetAccessToken,
    });

    globalThis.fetch = makeFetchMock([
      { status: 401, body: { detail: 'Expired', code: 'token_expired' } },
      { status: 200, body: { access_token: 'brand-new-token' } },
      { status: 200, body: {} },
    ]);

    await apiGet('/api/notes');
    expect(mockSetAccessToken).toHaveBeenCalledWith('brand-new-token');
  });

  // ----------- Error handling -----------

  it('throws ApiError with code and detail on 404', async () => {
    globalThis.fetch = makeFetchMock([
      { status: 404, body: { detail: 'Note not found', code: 'not_found' } },
    ]);

    let caught: ApiError | null = null;
    try {
      await apiGet('/api/notes/nonexistent');
    } catch (e) {
      caught = e as ApiError;
    }

    expect(caught).toBeInstanceOf(ApiError);
    expect(caught!.code).toBe('not_found');
    expect(caught!.detail).toBe('Note not found');
    expect(caught!.status).toBe(404);
  });

  it('throws ApiError on 500 without retry', async () => {
    const mockFetch = makeFetchMock([
      { status: 500, body: { detail: 'Internal server error', code: 'server_error' } },
    ]);
    globalThis.fetch = mockFetch;

    await expect(apiGet('/api/notes')).rejects.toThrow(ApiError);
    // Should not retry on 500
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});

describe('apiPost — fetch wrapper (Task 3.2)', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.clearAllMocks();
  });

  it('sends POST method', async () => {
    const mockFetch = makeFetchMock([{ status: 201, body: { id: 'new-id' } }]);
    globalThis.fetch = mockFetch;

    await apiPost('/api/notes', { content: 'hello', source_type: 'text' });

    const [_url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(init?.method).toBe('POST');
  });

  it('serializes body as JSON', async () => {
    const mockFetch = makeFetchMock([{ status: 201, body: { id: 'abc' } }]);
    globalThis.fetch = mockFetch;

    const requestBody = { content: 'test note', source_type: 'text' };
    await apiPost('/api/notes', requestBody);

    const [_url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(init?.body).toBe(JSON.stringify(requestBody));
  });

  it('returns parsed JSON on 201', async () => {
    const resp = { id: 'note-123', content: 'hello', source_type: 'text' };
    globalThis.fetch = makeFetchMock([{ status: 201, body: resp }]);

    const result = await apiPost('/api/notes', { content: 'hello' });
    expect(result).toEqual(resp);
  });

  it('attaches Authorization header', async () => {
    const mockFetch = makeFetchMock([{ status: 201, body: {} }]);
    globalThis.fetch = mockFetch;

    await apiPost('/api/notes', {});

    const [_url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const headers = init?.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer test-access-token');
  });
});

describe('apiPut — fetch wrapper (Task 3.2)', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.clearAllMocks();
  });

  it('sends PUT method', async () => {
    const mockFetch = makeFetchMock([{ status: 200, body: { id: 'note-1' } }]);
    globalThis.fetch = mockFetch;

    await apiPut('/api/notes/note-1', { content: 'updated' });

    const [_url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(init?.method).toBe('PUT');
  });
});

describe('apiDelete — fetch wrapper (Task 3.2)', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.clearAllMocks();
  });

  it('sends DELETE method', async () => {
    const mockFetch = makeFetchMock([{ status: 204, body: '' }]);
    globalThis.fetch = mockFetch;

    await apiDelete('/api/notes/note-1');

    const [_url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(init?.method).toBe('DELETE');
  });

  it('does not throw on 204 No Content', async () => {
    globalThis.fetch = makeFetchMock([{ status: 204, body: '' }]);

    await expect(apiDelete('/api/notes/note-1')).resolves.toBeUndefined();
  });

  it('throws ApiError on 403', async () => {
    globalThis.fetch = makeFetchMock([
      { status: 403, body: { detail: 'Forbidden', code: 'forbidden' } },
    ]);

    await expect(apiDelete('/api/notes/note-1')).rejects.toThrow(ApiError);
  });
});
