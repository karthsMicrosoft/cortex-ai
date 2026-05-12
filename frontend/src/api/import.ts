/**
 * Phase 5 / PR 5.1 — Frontend wrapper for /api/import/url.
 *
 * The backend endpoint (PR 5.2 — separate fleet agent) accepts a URL, fetches
 * + sanitizes the page server-side, and returns a NoteOut. This wrapper just
 * shapes the request so SharePage / shareInbox can call a typed function.
 */

import { apiPost } from './client';
import type { NoteOut } from './notes';

export interface ImportUrlRequest {
  url: string;
  title?: string;
}

export async function importUrl(req: ImportUrlRequest): Promise<NoteOut> {
  return apiPost<NoteOut>('/api/import/url', req);
}
