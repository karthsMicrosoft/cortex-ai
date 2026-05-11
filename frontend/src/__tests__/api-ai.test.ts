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

import { askCortex, askCortexStreaming } from '../api/ai';
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

// streaming tests appended below

// ---------------------------------------------------------------------------
// PR 4.4 — askCortexStreaming
// ---------------------------------------------------------------------------

/** Build a fetch that returns a ReadableStream from a sequence of UTF-8 chunks. */
function makeStreamingFetch(chunks: string[], opts: { status?: number } = {}) {
  const enc = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(enc.encode(c));
      controller.close();
    },
  });
  return vi.fn(async (_url: string, _init?: RequestInit) => {
    return {
      ok: (opts.status ?? 200) >= 200 && (opts.status ?? 200) < 300,
      status: opts.status ?? 200,
      statusText: 'OK',
      headers: { get: () => null },
      body: stream,
      json: async () => ({ detail: 'err' }),
    } as unknown as Response;
  });
}

describe('askCortexStreaming', () => {
  let originalFetch: typeof globalThis.fetch;
  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.clearAllMocks();
  });

  it('parses NDJSON and dispatches meta → tokens → done', async () => {
    globalThis.fetch = makeStreamingFetch([
      '{"type":"meta","retrieval_count":1,"model":"gpt-4o-mini"}\n',
      '{"type":"token","text":"Hi"}\n',
      '{"type":"token","text":" there"}\n',
      '{"type":"token","text":"."}\n',
      '{"type":"done","citations":[{"note_id":"n1","title":"t","snippet":"s","relevance":0.9}],"elapsed_ms":42}\n',
    ]);
    const tokens: string[] = [];
    let metaSeen: { retrieval_count: number; model: string } | null = null;
    let doneSeen: { count: number; ms: number } | null = null;

    await askCortexStreaming('q', {
      onMeta: (m) => { metaSeen = { retrieval_count: m.retrieval_count, model: m.model }; },
      onToken: (t) => tokens.push(t),
      onDone: (cits, ms) => { doneSeen = { count: cits.length, ms }; },
    });

    expect(metaSeen).toEqual({ retrieval_count: 1, model: 'gpt-4o-mini' });
    expect(tokens).toEqual(['Hi', ' there', '.']);
    expect(doneSeen).toEqual({ count: 1, ms: 42 });
  });

  it('handles partial chunks split across reads (1.5 lines per chunk)', async () => {
    globalThis.fetch = makeStreamingFetch([
      '{"type":"meta","retrieval_count":0,"model":"m"}\n{"type":"to',
      'ken","text":"A"}\n{"type":"token","text":"B"}\n',
      '{"type":"done","citations":[],"elapsed_ms":1}\n',
    ]);
    const tokens: string[] = [];
    let done = false;
    await askCortexStreaming('q', {
      onToken: (t) => tokens.push(t),
      onDone: () => { done = true; },
    });
    expect(tokens).toEqual(['A', 'B']);
    expect(done).toBe(true);
  });

  it('ignores invalid JSON lines but keeps reading', async () => {
    globalThis.fetch = makeStreamingFetch([
      '{"type":"meta","retrieval_count":0,"model":"m"}\n',
      'not-json-at-all\n',
      '{"type":"token","text":"X"}\n',
      '{"type":"done","citations":[],"elapsed_ms":0}\n',
    ]);
    const tokens: string[] = [];
    let errored = false;
    await askCortexStreaming('q', {
      onToken: (t) => tokens.push(t),
      onError: () => { errored = true; },
      onDone: () => undefined,
    });
    expect(tokens).toEqual(['X']);
    expect(errored).toBe(false);
  });

  it('handles premature stream end (no done frame)', async () => {
    globalThis.fetch = makeStreamingFetch([
      '{"type":"meta","retrieval_count":0,"model":"m"}\n',
      '{"type":"token","text":"partial"}\n',
    ]);
    const tokens: string[] = [];
    let doneCalled = false;
    let errorCalled = false;
    await askCortexStreaming('q', {
      onToken: (t) => tokens.push(t),
      onDone: () => { doneCalled = true; },
      onError: () => { errorCalled = true; },
    });
    expect(tokens).toEqual(['partial']);
    expect(doneCalled).toBe(false);
    expect(errorCalled).toBe(false);
  });

  it('dispatches error frame to onError', async () => {
    globalThis.fetch = makeStreamingFetch([
      '{"type":"meta","retrieval_count":1,"model":"m"}\n',
      '{"type":"error","detail":"upstream boom"}\n',
    ]);
    let errDetail = '';
    await askCortexStreaming('q', {
      onError: (d) => { errDetail = d; },
    });
    expect(errDetail).toBe('upstream boom');
  });

  it('sends Accept: application/x-ndjson and bearer token', async () => {
    const mockFetch = makeStreamingFetch([
      '{"type":"done","citations":[],"elapsed_ms":0}\n',
    ]);
    globalThis.fetch = mockFetch;
    await askCortexStreaming('hello?', { onDone: () => undefined });
    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const headers = init?.headers as Record<string, string>;
    expect(headers['Accept']).toBe('application/x-ndjson');
    expect(headers['Authorization']).toBe('Bearer test-access-token');
    expect(init?.method).toBe('POST');
    const body = JSON.parse(init?.body as string);
    expect(body.query).toBe('hello?');
  });

  it('passes signal through to fetch for cancellation', async () => {
    const mockFetch = makeStreamingFetch([
      '{"type":"done","citations":[],"elapsed_ms":0}\n',
    ]);
    globalThis.fetch = mockFetch;
    const ctrl = new AbortController();
    await askCortexStreaming('q', { signal: ctrl.signal, onDone: () => undefined });
    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(init?.signal).toBe(ctrl.signal);
  });
});
