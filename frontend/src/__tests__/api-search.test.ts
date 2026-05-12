/**
 * Phase 4 / Round 16 / PR 4.3 — api/search filter support TDD red
 *
 * The backend POST /api/search body accepts category / tags / date_from /
 * date_to. The frontend `search()` helper must forward our filter object
 * (which uses `since`/`until` field names — see SearchFiltersValue) onto the
 * request body, mapping them to the backend's `date_from`/`date_to` fields.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

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

import { search, listTags } from '../api/search';

let mockFetch: ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => [],
  });
  vi.stubGlobal('fetch', mockFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function getBody(): Record<string, unknown> {
  const init = mockFetch.mock.calls[0][1] as RequestInit;
  return JSON.parse(init.body as string);
}

describe('api/search — filter forwarding (P4 / R16 / PR 4.3)', () => {
  it('search() POSTs to /api/search with the query', async () => {
    await search({ query: 'leadership' });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toContain('/api/search');
    expect(getBody().query).toBe('leadership');
  });

  it('search() forwards category in the request body', async () => {
    await search({ query: 'q', category: 'Learning' });
    expect(getBody().category).toBe('Learning');
  });

  it('search() forwards tags as an array in the request body', async () => {
    await search({ query: 'q', tags: ['mentorship', 'book'] });
    expect(getBody().tags).toEqual(['mentorship', 'book']);
  });

  it('search() forwards date_from / date_to in the request body', async () => {
    await search({
      query: 'q',
      date_from: '2026-04-01',
      date_to: '2026-05-15',
    });
    const body = getBody();
    expect(body.date_from).toBe('2026-04-01');
    expect(body.date_to).toBe('2026-05-15');
  });

  it('search() omits filter fields when not provided', async () => {
    await search({ query: 'q' });
    const body = getBody();
    expect(body.category).toBeUndefined();
    expect(body.tags).toBeUndefined();
    expect(body.date_from).toBeUndefined();
    expect(body.date_to).toBeUndefined();
  });
});

describe('api/search — listTags() (P4 / R16 / PR 4.3)', () => {
  it('listTags() GETs /api/tags and returns parsed names', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => [
        { id: 't1', user_id: 'u1', name: 'mentorship', is_auto: false, created_at: '2026-01-01T00:00:00Z' },
        { id: 't2', user_id: 'u1', name: 'book',       is_auto: true,  created_at: '2026-01-02T00:00:00Z' },
      ],
    });
    const tags = await listTags();
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toContain('/api/tags');
    expect(tags).toEqual(['mentorship', 'book']);
  });
});

// ---------------------------------------------------------------------------
// Round 19 — title field on SearchResult
// ---------------------------------------------------------------------------

describe('api/search — title field (Round 19)', () => {
  it('parses title field from /api/search response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => [
        {
          id: 'n1',
          title: 'My titled note',
          content: 'body content',
          summary: 'sum',
          category: 'Ideas',
          created_at: '2026-05-01T00:00:00Z',
          semantic_score: 0.9,
          text_score: 0.5,
          combined_score: 0.78,
        },
      ],
    });
    const results = await search({ query: 'q' });
    expect(results).toHaveLength(1);
    expect(results[0].title).toBe('My titled note');
  });

  it('preserves null title from /api/search response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => [
        {
          id: 'n2',
          title: null,
          content: 'body',
          summary: null,
          category: 'Ideas',
          created_at: '2026-05-01T00:00:00Z',
          semantic_score: 0.9,
          text_score: 0.5,
          combined_score: 0.78,
        },
      ],
    });
    const results = await search({ query: 'q' });
    expect(results[0].title ?? null).toBeNull();
  });
});
