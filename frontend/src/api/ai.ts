/**
 * api/ai.ts — Phase 4 / Round 16 / PR 4.2 (Ask UI)
 *
 * Typed wrapper around POST /api/ai/answer (RAG endpoint). Mirrors the
 * notes.ts style — thin facade over the shared apiPost client so we get
 * Authorization-Bearer headers, 401-refresh-and-retry, and ApiError for free.
 *
 * On HTTP 429 the underlying client populates `ApiError.retryAfter` (seconds)
 * from the `Retry-After` header so callers (AskPage) can render a friendly
 * "try again in N minutes" message.
 */

import { apiPost } from './client';

// ---------------------------------------------------------------------------
// Backend schema mirrors (see backend/app/schemas/ai_answer.py)
// ---------------------------------------------------------------------------

export type AnswerCitation = {
  note_id: string;
  title: string;
  snippet: string;
  relevance: number;
};

export type AnswerResponse = {
  answer: string;
  citations: AnswerCitation[];
  model: string;
  retrieval_count: number;
  elapsed_ms: number;
};

export type AnswerFilters = {
  category?: string;
  tags?: string[];
  since?: string;
  until?: string;
};

export type AskOptions = {
  max_results?: number;
  filters?: AnswerFilters;
};

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function askCortex(
  query: string,
  opts: AskOptions = {},
): Promise<AnswerResponse> {
  const body: Record<string, unknown> = { query };
  if (opts.max_results !== undefined) body.max_results = opts.max_results;
  if (opts.filters !== undefined) body.filters = opts.filters;
  return apiPost<AnswerResponse>('/api/ai/answer', body);
}
