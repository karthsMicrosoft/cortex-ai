/**
 * Phase 5 / PR 5.1 — Shared inbox service.
 *
 * Wraps the Dexie `shared_inbox` table with a small enqueue/peek/drain API.
 *
 * Use case: a logged-out user lands on /share via the OS share sheet. We
 * cannot POST without an access token, so the SharePage stashes the payload
 * here and redirects to /login. After auth completes, SessionGate calls
 * drain() to replay every pending share through /api/import/url (URL only)
 * or /api/notes (text / text+url).
 */

import { db, type SharedInboxEntry } from '../db';
import { createNote } from '../api/notes';
import { importUrl } from '../api/import';

export interface SharedPayload {
  title?: string;
  text?: string;
  url?: string;
}

/** Combine title/text/url into a single text-note body. */
export function composeNoteBody(payload: SharedPayload): string {
  const parts: string[] = [];
  if (payload.title) parts.push(payload.title);
  if (payload.text) parts.push(payload.text);
  if (payload.url) parts.push(payload.url);
  return parts.join('\n\n').trim();
}

/** Add a payload to the inbox. Records ISO timestamp for ordering. */
export async function enqueue(payload: SharedPayload): Promise<void> {
  await db.shared_inbox.add({
    title: payload.title,
    text: payload.text,
    url: payload.url,
    created_at: new Date().toISOString(),
  });
}

/** Return the most-recently enqueued payload, or null if the inbox is empty. */
export async function peek(): Promise<SharedPayload | null> {
  const rows = await db.shared_inbox.orderBy('created_at').reverse().limit(1).toArray();
  if (rows.length === 0) return null;
  const r = rows[0];
  return { title: r.title, text: r.text, url: r.url };
}

/**
 * Process every entry in the inbox. URL-only entries go to /api/import/url;
 * everything else (text-only or text+url) goes to /api/notes with the URL
 * appended to the body. Successful entries are deleted; failed entries stay
 * in the table so a future drain can retry them.
 *
 * Returns the number of entries that were processed successfully.
 */
export async function drain(): Promise<number> {
  const rows: SharedInboxEntry[] = await db.shared_inbox.orderBy('created_at').toArray();
  let succeeded = 0;
  for (const row of rows) {
    try {
      await processOne(row);
      if (row.id !== undefined) {
        await db.shared_inbox.delete(row.id);
      }
      succeeded += 1;
    } catch {
      // Leave the row in the table for the next drain attempt.
    }
  }
  return succeeded;
}

async function processOne(row: SharedInboxEntry): Promise<void> {
  const hasText = Boolean(row.text && row.text.trim());
  const hasTitle = Boolean(row.title && row.title.trim());
  if (row.url && !hasText && !hasTitle) {
    await importUrl({ url: row.url });
    return;
  }
  const content = composeNoteBody({ title: row.title, text: row.text, url: row.url });
  if (!content) return;
  await createNote({
    content,
    source_type: 'text',
  });
}
