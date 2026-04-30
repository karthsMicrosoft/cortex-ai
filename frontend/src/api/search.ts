import { apiGet, apiPost } from './client';
import type { Category } from './notes';

// ---------------------------------------------------------------------------
// Search types
// ---------------------------------------------------------------------------

export interface SearchRequest {
  query: string;
  category?: Category;
  tags?: string[];
  date_from?: string;
  date_to?: string;
  limit?: number;
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

export async function search(req: SearchRequest): Promise<SearchResult[]> {
  return apiPost<SearchResult[]>('/api/search', req);
}

export async function searchSimilar(noteId: string): Promise<SearchResult[]> {
  return apiGet<SearchResult[]>(`/api/search/similar/${noteId}`);
}
