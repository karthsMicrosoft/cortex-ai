/**
 * Phase 5 / PR 5.1 — AuthGate / SessionGate share-inbox drain integration
 *
 * After authentication completes (either via SessionGate's silent refresh on
 * boot or via a fresh login that flips accessToken in the store), any pending
 * shared payloads stashed while the user was logged out must be drained and
 * processed via shareInbox.drain().
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act } from '@testing-library/react';

// --- API + sync mocks (SessionGate touches refresh + me + syncManager) ---
vi.mock('../api/auth', () => ({
  refresh: vi.fn().mockRejectedValue(new Error('no cookie')),
  me: vi.fn(),
}));
vi.mock('../sync/syncManager', () => ({
  syncManager: { start: vi.fn(), stop: vi.fn() },
}));

// --- shareInbox drain spy ---
vi.mock('../services/shareInbox', () => ({
  enqueue: vi.fn().mockResolvedValue(undefined),
  drain: vi.fn().mockResolvedValue(0),
  peek: vi.fn().mockResolvedValue(null),
}));

import { SessionGate } from '../components/SessionGate';
import { useAuthStore } from '../store/authStore';
import * as shareInbox from '../services/shareInbox';

beforeEach(() => {
  vi.clearAllMocks();
  // Reset the store between tests so accessToken transitions are observable.
  useAuthStore.setState({ accessToken: null, user: null, isRestoring: false });
});

describe('SessionGate — share-inbox drain on auth', () => {
  it('calls shareInbox.drain() when accessToken transitions to truthy', async () => {
    render(
      <SessionGate>
        <div>child</div>
      </SessionGate>,
    );

    // Simulate fresh login: store flips accessToken.
    await act(async () => {
      useAuthStore.setState({
        accessToken: 'tok',
        user: { id: 'u1', email: 'a@b.c' },
        isRestoring: false,
      });
    });

    expect(shareInbox.drain).toHaveBeenCalled();
  });

  it('does not call drain() when there is no access token', async () => {
    render(
      <SessionGate>
        <div>child</div>
      </SessionGate>,
    );
    // Allow any mount effects to flush
    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });
    expect(shareInbox.drain).not.toHaveBeenCalled();
  });
});
