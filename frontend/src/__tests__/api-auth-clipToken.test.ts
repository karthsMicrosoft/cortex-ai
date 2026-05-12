/**
 * api-auth-clipToken.test.ts — Round 19 / PR C (TDD red)
 *
 * Tests for frontend/src/api/auth.ts::mintClipToken() — POSTs to
 * /api/auth/clip-token and returns { clip_token, expires_in, scope }.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock authStore so the client picks up an access token via apiPost
vi.mock('../store/authStore', () => {
  const state = {
    accessToken: 'test-token',
    user: { id: 'u1' },
    setAccessToken: vi.fn(),
    logout: vi.fn(),
  };
  const store = Object.assign(
    (selector: (s: typeof state) => unknown) => selector(state),
    { getState: () => state, subscribe: () => () => {}, setState: () => {} },
  );
  return { useAuthStore: store };
});

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    headers: {
      get: (name: string) => headers[name.toLowerCase()] ?? null,
    },
    json: async () => body,
  } as unknown as Response;
}

describe('mintClipToken (api/auth.ts)', () => {
  it('POSTs to /api/auth/clip-token with auth header', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { clip_token: 'jwt.abc.def', expires_in: 2592000, scope: 'clip' }),
    );

    const { mintClipToken } = await import('../api/auth');
    await mintClipToken();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/api\/auth\/clip-token$/);
    expect(init.method).toBe('POST');
    const headers = init.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer test-token');
  });

  it('returns clip_token + expires_in + scope', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { clip_token: 'jwt.payload.sig', expires_in: 2592000, scope: 'clip' }),
    );

    const { mintClipToken } = await import('../api/auth');
    const result = await mintClipToken();

    expect(result.clip_token).toBe('jwt.payload.sig');
    expect(result.expires_in).toBe(2592000);
    expect(result.scope).toBe('clip');
  });

  it('throws ApiError on 401', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, { code: 'unauthorized', detail: 'Not authenticated' }),
    );
    // Refresh attempt also fails so we don't loop
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, { code: 'unauthorized', detail: 'no refresh' }),
    );

    const { mintClipToken } = await import('../api/auth');
    const { ApiError } = await import('../api/client');

    await expect(mintClipToken()).rejects.toBeInstanceOf(ApiError);
  });

  it('throws ApiError on 429 (rate limit)', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(429, { code: 'rate_limited', detail: 'Slow down' }, { 'retry-after': '60' }),
    );

    const { mintClipToken } = await import('../api/auth');
    const { ApiError } = await import('../api/client');

    try {
      await mintClipToken();
      throw new Error('expected throw');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as InstanceType<typeof ApiError>).status).toBe(429);
    }
  });
});
