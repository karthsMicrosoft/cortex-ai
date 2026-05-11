/**
 * api/ai.ts — Phase 4 / Round 16 / PR 4.2 (Ask UI) + PR 4.4 (streaming)
 *
 * Typed wrapper around POST /api/ai/answer (RAG endpoint). Mirrors the
 * notes.ts style — thin facade over the shared apiPost client so we get
 * Authorization-Bearer headers, 401-refresh-and-retry, and ApiError for free.
 *
 * On HTTP 429 the underlying client populates `ApiError.retryAfter` (seconds)
 * from the `Retry-After` header so callers (AskPage) can render a friendly
 * "try again in N minutes" message.
 *
 * PR 4.4 adds `askCortexStreaming` — same endpoint, but with
 * `Accept: application/x-ndjson` so the server returns a token stream.
 * EventSource cannot be used because it cannot carry the bearer token.
 */

import { apiPost } from './client';
import { ApiError, apiUrl } from './client';
import { useAuthStore } from '../store/authStore';

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

export type PriorMessage = {
  role: 'user' | 'assistant';
  content: string;
};

export type AskOptions = {
  max_results?: number;
  filters?: AnswerFilters;
  prior_messages?: PriorMessage[];
};

// ---------------------------------------------------------------------------
// Public API — non-streaming
// ---------------------------------------------------------------------------

export async function askCortex(
  query: string,
  opts: AskOptions = {},
): Promise<AnswerResponse> {
  const body: Record<string, unknown> = { query };
  if (opts.max_results !== undefined) body.max_results = opts.max_results;
  if (opts.filters !== undefined) body.filters = opts.filters;
  if (opts.prior_messages !== undefined) body.prior_messages = opts.prior_messages;
  return apiPost<AnswerResponse>('/api/ai/answer', body);
}

// ---------------------------------------------------------------------------
// Streaming (PR 4.4) — NDJSON over fetch + ReadableStream
// ---------------------------------------------------------------------------

export type StreamMetaFrame = {
  type: 'meta';
  retrieval_count: number;
  model: string;
};
export type StreamTokenFrame = { type: 'token'; text: string };
export type StreamDoneFrame = {
  type: 'done';
  citations: AnswerCitation[];
  elapsed_ms: number;
};
export type StreamErrorFrame = { type: 'error'; detail: string };

export type StreamCallbacks = {
  onMeta?: (m: StreamMetaFrame) => void;
  onToken?: (text: string) => void;
  onDone?: (citations: AnswerCitation[], elapsedMs: number) => void;
  onError?: (detail: string) => void;
  signal?: AbortSignal;
};

/** True when the runtime supports `Response.body.getReader()`. */
export function streamingSupported(): boolean {
  if (typeof globalThis === 'undefined' || typeof globalThis.fetch !== 'function') {
    return false;
  }
  return typeof ReadableStream !== 'undefined' && typeof TextDecoder !== 'undefined';
}

/**
 * Stream a RAG answer via NDJSON. Resolves once the stream ends (done | error
 * | aborted). All frames are reported via the supplied callbacks.
 *
 * Falls back to a single non-streaming call when the runtime cannot stream
 * (very old browsers).
 */
export async function askCortexStreaming(
  query: string,
  opts: AskOptions & StreamCallbacks = {},
): Promise<void> {
  if (!streamingSupported()) {
    try {
      const r = await askCortex(query, opts);
      opts.onMeta?.({
        type: 'meta',
        retrieval_count: r.retrieval_count,
        model: r.model,
      });
      opts.onToken?.(r.answer);
      opts.onDone?.(r.citations, r.elapsed_ms);
    } catch (e) {
      const detail =
        e instanceof ApiError ? e.detail : e instanceof Error ? e.message : 'Unknown error';
      opts.onError?.(detail);
    }
    return;
  }

  const body: Record<string, unknown> = { query };
  if (opts.max_results !== undefined) body.max_results = opts.max_results;
  if (opts.filters !== undefined) body.filters = opts.filters;
  if (opts.prior_messages !== undefined) body.prior_messages = opts.prior_messages;

  const { accessToken } = useAuthStore.getState();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/x-ndjson',
  };
  if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;

  let res: Response;
  try {
    res = await fetch(apiUrl('/api/ai/answer'), {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      credentials: 'include',
      signal: opts.signal,
    });
  } catch (e) {
    if ((e as { name?: string })?.name === 'AbortError') return;
    opts.onError?.(e instanceof Error ? e.message : 'Network error');
    return;
  }

  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;
    try {
      const j = (await res.json()) as { detail?: string };
      if (j?.detail) detail = j.detail;
    } catch {
      // body wasn't JSON — keep statusText fallback
    }
    opts.onError?.(detail);
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    opts.onError?.('Response stream not available');
    return;
  }

  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const handleLine = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    let frame: { type?: string; [k: string]: unknown };
    try {
      frame = JSON.parse(trimmed);
    } catch {
      return; // ignore malformed line per spec
    }
    switch (frame.type) {
      case 'meta':
        opts.onMeta?.(frame as unknown as StreamMetaFrame);
        break;
      case 'token':
        opts.onToken?.(String(frame.text ?? ''));
        break;
      case 'done': {
        const f = frame as unknown as StreamDoneFrame;
        opts.onDone?.(f.citations ?? [], f.elapsed_ms ?? 0);
        break;
      }
      case 'error':
        opts.onError?.(String(frame.detail ?? 'Unknown stream error'));
        break;
      default:
        break;
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newlineIdx = buffer.indexOf('\n');
      while (newlineIdx !== -1) {
        const line = buffer.slice(0, newlineIdx);
        buffer = buffer.slice(newlineIdx + 1);
        handleLine(line);
        newlineIdx = buffer.indexOf('\n');
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) handleLine(buffer);
  } catch (e) {
    if ((e as { name?: string })?.name === 'AbortError') return;
    opts.onError?.(e instanceof Error ? e.message : 'Stream read error');
  }
}
