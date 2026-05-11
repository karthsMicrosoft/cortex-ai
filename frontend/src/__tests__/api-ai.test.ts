/**
 * api-ai.test.ts — Phase 4 / Round 16 / PR 4.2 (Ask UI)
 *
 * TDD tests for `frontend/src/api/ai.ts` — typed wrapper around
 * POST /api/ai/answer. Mirrors the api-client.test.ts pattern.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Hoisted mock for authStore (matches api-client.test.ts pattern).
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

import { askCortex } from '../api/ai';
import { ApiError } from '../api/client';

// ---------------------------------------------------------------------------
// fetch mock helper — mirrors api-client.test.ts
// ---------------------------------------------------------------------------

function makeFetchMock(
  responses: Array<{ status: number; body: unknown; headers?: Record<string, string> }>,
) {
  let i = 0;
  return vi.fn(async (_url: string, _init?: RequestInit) => {
    const r = responses[Math.min(i, responses.length - 1)];
    i++;
    return {
      ok: r.status >= 200 && r.status < 300,
      status: r.status,
      statusText: r.status === 200 ? 'OK' : 'Error',
      headers: {
        get: (name: string) => r.headers?.[name.toLowerCase()] ?? null,
      },
      json: async () => r.body,
    } as unknown as Response;
  });
}

const SAMPLE_RESPONSE = {
  answer: 'Leadership is about service [1].',
  citations: [
    { note_id: 'n-1', title: 'On leadership', snippet: 'serve first', relevance: 0.9 },
  ],
  model: 'gpt-4o-mini',
  retrieval_count: 1,
  elapsed_ms: 1234,
};

describe('askCortex', () => {
  let originalFetch: typeof globalThis.fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.clearAllMocks();
  });

  it('POSTs to /api/ai/answer with auth header and JSON body', async () => {
    const mockFetch = makeFetchMock([{ status: 200, body: SAMPLE_RESPONSE }]);
    globalThis.fetch = mockFetch;

    const out = await askCortex('how do i lead?');

    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/ai/answer');
    expect(init?.method).toBe('POST');
    const headers = init?.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer test-access-token');
    expect(headers['Content-Type']).toBe('application/json');
    const body = JSON.parse(init?.body as string);
    expect(body.query).toBe('how do i lead?');
    expect(out.answer).toBe(SAMPLE_RESPONSE.answer);
    expect(out.citations).toHaveLength(1);
  });

  it('throws ApiError on 500', async () => {
    globalThis.fetch = makeFetchMock([
      { status: 500, body: { detail: 'boom', code: 'server_error' } },
    ]);

    await expect(askCortex('x')).rejects.toThrow(ApiError);
  });

  it('passes filters and max_results through', async () => {
    const mockFetch = makeFetchMock([{ status: 200, body: SAMPLE_RESPONSE }]);
    globalThis.fetch = mockFetch;

    await askCortex('q', {
      max_results: 5,
      filters: { category: 'Journal', tags: ['x'], since: '2025-01-01', until: '2025-12-31' },
    });

    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init?.body as string);
    expect(body.max_results).toBe(5);
    expect(body.filters).toEqual({
      category: 'Journal',
      tags: ['x'],
      since: '2025-01-01',
      until: '2025-12-31',
    });
  });

  it('429 attaches Retry-After (seconds) on the thrown ApiError', async () => {
    globalThis.fetch = makeFetchMock([
      {
        status: 429,
        body: { detail: 'rate limited', code: 'rate_limited' },
        headers: { 'retry-after': '120' },
      },
    ]);

    let caught: unknown = null;
    try {
      await askCortex('q');
    } catch (e) {
      caught = e;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).status).toBe(429);
    expect((caught as ApiError & { retryAfter?: number }).retryAfter).toBe(120);
  });
});
