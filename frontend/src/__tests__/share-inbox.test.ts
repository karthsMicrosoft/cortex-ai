/**
 * Phase 5 / PR 5.1 — shareInbox service tests
 *
 * Verifies the Dexie-backed pending-share inbox used to stash share payloads
 * received while the user is logged out. After login the AuthGate / SessionGate
 * calls drain() to process every pending share and clear the table.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock the API surface so drain() doesn't make real network calls.
vi.mock('../api/notes', () => ({
  createNote: vi.fn(),
}));
vi.mock('../api/import', () => ({
  importUrl: vi.fn(),
}));

import { db } from '../db';
import * as shareInbox from '../services/shareInbox';
import { createNote } from '../api/notes';
import { importUrl } from '../api/import';

beforeEach(async () => {
  vi.clearAllMocks();
  await db.shared_inbox.clear();
});

describe('shareInbox.enqueue', () => {
  it('stores a payload in Dexie', async () => {
    await shareInbox.enqueue({ url: 'https://example.com/article' });
    const rows = await db.shared_inbox.toArray();
    expect(rows.length).toBe(1);
    expect(rows[0].url).toBe('https://example.com/article');
    expect(rows[0].created_at).toBeTruthy();
  });

  it('stamps created_at as ISO string', async () => {
    await shareInbox.enqueue({ text: 'hello' });
    const rows = await db.shared_inbox.toArray();
    expect(typeof rows[0].created_at).toBe('string');
    // ISO 8601 format check
    expect(rows[0].created_at).toMatch(/\d{4}-\d{2}-\d{2}T/);
  });
});

describe('shareInbox.peek', () => {
  it('returns null when the inbox is empty', async () => {
    const result = await shareInbox.peek();
    expect(result).toBeNull();
  });

  it('returns the most recent payload', async () => {
    await shareInbox.enqueue({ text: 'older' });
    await new Promise((r) => setTimeout(r, 5));
    await shareInbox.enqueue({ text: 'newer' });
    const result = await shareInbox.peek();
    expect(result?.text).toBe('newer');
  });
});

describe('shareInbox.drain', () => {
  it('does nothing when inbox is empty', async () => {
    const count = await shareInbox.drain();
    expect(count).toBe(0);
    expect(createNote).not.toHaveBeenCalled();
    expect(importUrl).not.toHaveBeenCalled();
  });

  it('calls importUrl for url-only payloads', async () => {
    vi.mocked(importUrl).mockResolvedValue({ id: 'n1' } as never);
    await shareInbox.enqueue({ url: 'https://example.com/a' });
    const count = await shareInbox.drain();
    expect(count).toBe(1);
    expect(importUrl).toHaveBeenCalledWith({ url: 'https://example.com/a' });
    const rows = await db.shared_inbox.toArray();
    expect(rows.length).toBe(0);
  });

  it('calls createNote for text-only payloads', async () => {
    vi.mocked(createNote).mockResolvedValue({ id: 'n2' } as never);
    await shareInbox.enqueue({ text: 'a quick thought' });
    const count = await shareInbox.drain();
    expect(count).toBe(1);
    expect(createNote).toHaveBeenCalledWith(
      expect.objectContaining({
        content: expect.stringContaining('a quick thought'),
        source_type: 'text',
      }),
    );
    expect((await db.shared_inbox.toArray()).length).toBe(0);
  });

  it('combines text + url into the createNote body when both are present', async () => {
    vi.mocked(createNote).mockResolvedValue({ id: 'n3' } as never);
    await shareInbox.enqueue({ text: 'check this', url: 'https://example.com/x' });
    await shareInbox.drain();
    expect(createNote).toHaveBeenCalledTimes(1);
    const arg = vi.mocked(createNote).mock.calls[0][0];
    expect(arg.content).toContain('check this');
    expect(arg.content).toContain('https://example.com/x');
  });

  it('processes multiple entries and clears them all', async () => {
    vi.mocked(importUrl).mockResolvedValue({ id: 'a' } as never);
    vi.mocked(createNote).mockResolvedValue({ id: 'b' } as never);
    await shareInbox.enqueue({ url: 'https://example.com/1' });
    await shareInbox.enqueue({ text: 'two' });
    await shareInbox.enqueue({ url: 'https://example.com/3' });

    const count = await shareInbox.drain();
    expect(count).toBe(3);
    expect((await db.shared_inbox.toArray()).length).toBe(0);
  });

  it('keeps failed entries in the inbox and reports successful count', async () => {
    vi.mocked(importUrl)
      .mockResolvedValueOnce({ id: 'ok' } as never)
      .mockRejectedValueOnce(new Error('500'));
    await shareInbox.enqueue({ url: 'https://ok.example.com' });
    await shareInbox.enqueue({ url: 'https://bad.example.com' });

    const count = await shareInbox.drain();
    expect(count).toBe(1);
    const remaining = await db.shared_inbox.toArray();
    expect(remaining.length).toBe(1);
    expect(remaining[0].url).toBe('https://bad.example.com');
  });
});
