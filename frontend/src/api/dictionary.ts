/**
 * Typed API client for the Personal Dictionary endpoints.
 *
 * Wraps /api/dictionary (CRUD, bulk import, export).
 */
import { apiDelete, apiGet, apiPost, apiPut } from './client';

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export type TermType =
  | 'name'
  | 'music_term'
  | 'technical'
  | 'place'
  | 'acronym'
  | 'general';

export interface VocabularyTermOut {
  id: string;
  user_id: string;
  term: string;
  term_type: TermType;
  pronunciation_hint?: string | null;
  boost_weight: number;
  usage_count: number;
  created_at: string;
  updated_at: string;
}

export interface VocabularyTermCreate {
  term: string;
  term_type?: TermType;
  pronunciation_hint?: string | null;
  boost_weight?: number;
}

export interface VocabularyTermUpdate {
  term?: string;
  term_type?: TermType;
  pronunciation_hint?: string | null;
  boost_weight?: number;
}

export interface BulkImportResponse {
  inserted: number;
  total: number;
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

/**
 * List all vocabulary terms for the current user, optionally filtered by type.
 */
export function listTerms(filter?: { term_type?: TermType }): Promise<VocabularyTermOut[]> {
  const params = filter?.term_type ? `?term_type=${filter.term_type}` : '';
  return apiGet<VocabularyTermOut[]>(`/api/dictionary${params}`);
}

/**
 * Add a new vocabulary term.
 * Throws ApiError with status 400 if the 2000-term limit is reached.
 * Throws ApiError with status 409 if the term already exists.
 */
export function addTerm(payload: VocabularyTermCreate): Promise<VocabularyTermOut> {
  return apiPost<VocabularyTermOut>('/api/dictionary', payload);
}

/**
 * Update an existing vocabulary term by id.
 */
export function updateTerm(id: string, patch: VocabularyTermUpdate): Promise<VocabularyTermOut> {
  return apiPut<VocabularyTermOut>(`/api/dictionary/${id}`, patch);
}

/**
 * Delete a vocabulary term by id.
 */
export function deleteTerm(id: string): Promise<void> {
  return apiDelete(`/api/dictionary/${id}`);
}

/**
 * Bulk import up to 500 terms.
 * Throws ApiError with status 400 if the list exceeds 500 entries.
 * Returns { inserted, total } — duplicates are skipped, not errors.
 */
export function bulkImport(terms: VocabularyTermCreate[]): Promise<BulkImportResponse> {
  return apiPost<BulkImportResponse>('/api/dictionary/bulk', terms);
}

/**
 * Export all vocabulary terms as a JSON list.
 */
export function exportTerms(): Promise<VocabularyTermOut[]> {
  return apiGet<VocabularyTermOut[]>('/api/dictionary/export');
}
