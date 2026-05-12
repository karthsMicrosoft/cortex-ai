/**
 * api-links.test.ts — PR 6.1 (Backlinks API client)
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

import { getNoteLinks } from '../api/links';
import { ApiError } from '../api/client';

let mockFetch: ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch = vi.fn();
  vi.stubGlobal('fetch', mockFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('api/links — getNoteLinks (PR 6.1)', () => {
  it('calls /api/notes/{id}/links with auth header', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ outgoing: [], incoming: [] }),
    });
    await getNoteLinks('abc-123');
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const url = mockFetch.mock.calls[0][0] as string;
    const init = mockFetch.mock.calls[0][1] as RequestInit;
    expect(url).toContain('/api/notes/abc-123/links');
    expect((init.headers as Record<string, string>)['Authorization']).toBe(
      'Bearer test-access-token',
    );
    expect(init.method).toBe('GET');
  });

  it('throws ApiError on 404', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      headers: { get: () => null },
      json: async () => ({ code: 'not_found', detail: 'Note not found' }),
    });
    await expect(getNoteLinks('missing')).rejects.toBeInstanceOf(ApiError);
  });

  it('parses outgoing and incoming arrays', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        outgoing: [
          {
            note_id: 'n1',
            title: 'A',
            summary: 's',
            category: 'Ideas',
            link_type: 'semantic',
            score: 0.87,
          },
        ],
        incoming: [
          {
            note_id: 'n2',
            title: null,
            summary: null,
            category: 'Learning',
            link_type: 'wiki',
            score: null,
          },
        ],
      }),
    });
    const data = await getNoteLinks('abc');
    expect(data.outgoing).toHaveLength(1);
    expect(data.outgoing[0].note_id).toBe('n1');
    expect(data.outgoing[0].score).toBe(0.87);
    expect(data.outgoing[0].link_type).toBe('semantic');
    expect(data.incoming).toHaveLength(1);
    expect(data.incoming[0].note_id).toBe('n2');
    expect(data.incoming[0].link_type).toBe('wiki');
    expect(data.incoming[0].score).toBeNull();
  });
});
