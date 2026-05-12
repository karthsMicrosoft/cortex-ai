import { apiGet } from './client';

// ---------------------------------------------------------------------------
// Backlinks API — PR 6.1
// ---------------------------------------------------------------------------

export interface NoteLinkItem {
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
