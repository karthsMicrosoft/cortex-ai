/**
 * App.lazy.test.tsx — TDD red phase
 *
 * PERF: verify that the route-level pages listed below are lazy-loaded via
 * React.lazy + Suspense in `frontend/src/App.tsx`. While the chunk is
 * downloading, the `RouteLoading` fallback (role="status") must render.
 * Once the chunk resolves, the page content should appear.
 *
 * Routes verified:
 *   /insights, /create, /settings, /library, /search, /note/:id
 *
 * Strategy:
 *   - Mock the heavy/networked dependencies inside each page so that when
 *     React resolves the lazy import, the page renders deterministically in
 *     jsdom without firing real fetches.
 *   - Pre-authenticate via the auth store so AuthGate does not redirect to
 *     /login.
 *   - Use `findByRole`/`findByText` (waits) rather than `getBy*` because the
 *     lazy chunk import is asynchronous.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Heavy / networked module mocks — keep page renders cheap & deterministic.
// ---------------------------------------------------------------------------

vi.mock('../api/auth', () => ({
  refresh: vi.fn().mockRejectedValue(new Error('no cookie')),
  me: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
  changePassword: vi.fn(),
}));

vi.mock('../sync/syncManager', () => ({
  syncManager: { start: vi.fn(), stop: vi.fn() },
}));

vi.mock('react-force-graph-2d', () => ({
  default: () => <div data-testid="force-graph" />,
}));

// Mock fetch globally — pages that auto-fetch on mount get an empty response.
beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [], notes: [], results: [], insights: [] }),
      text: async () => '',
    }) as unknown as typeof fetch,
  );
});

// ---------------------------------------------------------------------------
// Auth bootstrap — make AuthGate think we are signed in.
// ---------------------------------------------------------------------------

import { useAuthStore } from '../store/authStore';
import App from '../App';

function authenticate() {
  useAuthStore.setState({
    accessToken: 'test-token',
    user: { id: 'u1', email: 't@example.com' } as never,
    isRestoring: false,
  });
}

function renderAt(path: string) {
  authenticate();
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('App lazy-loaded routes', () => {
  const lazyRoutes = ['/insights', '/create', '/settings', '/library', '/search', '/note/some-id'];

  for (const route of lazyRoutes) {
    it(`shows the RouteLoading fallback while ${route} is loading`, async () => {
      renderAt(route);
      // The Suspense fallback for a lazy chunk renders synchronously the first
      // time React encounters the boundary, so it should be present in the
      // initial render. RouteLoading uses role="status".
      const fallback = await screen.findByRole('status', { name: /loading page/i });
      expect(fallback).toBeInTheDocument();
    });
  }
});
