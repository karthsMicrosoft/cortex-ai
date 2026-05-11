import { apiGet, apiPost } from './client';
import type { Category } from './notes';

// ---------------------------------------------------------------------------
// Search types
// ---------------------------------------------------------------------------

export interface SearchRequest {
  query: string;
  category?: Category | string;
  tags?: string[];
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export interface SearchResult {
  id: string;
  content: string;
  summary?: string;
  category: Category;
  created_at: string;
  semantic_score: number;
  text_score: number;
  combined_score: number;
}

// ---------------------------------------------------------------------------
// Search API functions
// ---------------------------------------------------------------------------

/**
 * POST /api/search — hybrid semantic + full-text.
 *
 * Forwards optional filters (category, tags, date_from, date_to) onto the
 * request body. The backend treats undefined fields as no-op (see SQL in
 * backend/app/api/search.py).
 */
export async function search(req: SearchRequest): Promise<SearchResult[]> {
  // Strip undefined values so the body stays clean — Pydantic accepts both
  // missing keys and explicit nulls, but omitting is more idiomatic and
  // matches the existing test fixtures.
  const body: Record<string, unknown> = { query: req.query };
  if (req.category !== undefined) body.category = req.category;
  if (req.tags !== undefined && req.tags.length > 0) body.tags = req.tags;
  if (req.date_from !== undefined) body.date_from = req.date_from;
  if (req.date_to !== undefined) body.date_to = req.date_to;
  if (req.limit !== undefined) body.limit = req.limit;
  if (req.offset !== undefined) body.offset = req.offset;
  return apiPost<SearchResult[]>('/api/search', body);
}

export async function searchSimilar(noteId: string): Promise<SearchResult[]> {
  return apiGet<SearchResult[]>(`/api/search/similar/${noteId}`);
}

// ---------------------------------------------------------------------------
// Tags helper — used by SearchFilters to populate the chip list
// ---------------------------------------------------------------------------

interface TagOut {
  id: string;
  user_id: string;
  name: string;
  is_auto: boolean;
  created_at: string;
}

/**
 * GET /api/tags — return the distinct tag names for the authenticated user,
 * ordered as the backend returns them (alphabetical).
 */
export async function listTags(): Promise<string[]> {
  const tags = await apiGet<TagOut[]>('/api/tags');
  return tags.map((t) => t.name);
}
