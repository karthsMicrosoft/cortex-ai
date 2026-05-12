import { apiDelete, apiGet, apiPost } from './client';

// ---------------------------------------------------------------------------
// Backlinks API — PR 6.1
// ---------------------------------------------------------------------------

export interface NoteLinkItem {
  link_id: string | null;
  note_id: string;
  title: string | null;
  summary: string | null;
  category: string;
  link_type: string; // 'manual' | 'wiki' | 'semantic' (open-ended for forward-compat)
  score: number | null;
}

export interface NoteLinksResponse {
  outgoing: NoteLinkItem[];
  incoming: NoteLinkItem[];
}

/**
 * Fetch outgoing + incoming links for a note.
 *
 * GET /api/notes/{noteId}/links
 */
export async function getNoteLinks(noteId: string): Promise<NoteLinksResponse> {
  return apiGet<NoteLinksResponse>(`/api/notes/${noteId}/links`);
}

// ---------------------------------------------------------------------------
// Manual link CRUD — PR 6.3
// ---------------------------------------------------------------------------

export interface NoteLink {
  id: string;
  source_note_id: string;
  target_note_id: string;
  link_type: string;
  score: number | null;
  created_at: string | null;
}

/**
 * Create a manual link from `sourceId` → `targetId`.
 *
 * POST /api/notes/{sourceId}/links
 *
 * Server is idempotent — repeating the call returns the existing row
 * with HTTP 200 instead of 201, both surfaced as the same `NoteLink`.
 */
export async function createManualLink(
  sourceId: string,
  targetId: string,
): Promise<NoteLink> {
  return apiPost<NoteLink>(`/api/notes/${sourceId}/links`, {
    target_note_id: targetId,
    link_type: 'manual',
  });
}

/**
 * Delete a manual link by id (under a given source note).
 *
 * DELETE /api/notes/{sourceId}/links/{linkId}
 */
export async function deleteLink(sourceId: string, linkId: string): Promise<void> {
  return apiDelete(`/api/notes/${sourceId}/links/${linkId}`);
}
