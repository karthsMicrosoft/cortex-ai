/**
 * AskPage — Phase 4 / Round 16 / PR 4.2.
 *
 * Conversational entry point: user asks a natural-language question, we POST
 * to /api/ai/answer (RAG over their notes) and render the grounded answer
 * with inline citation chips and citation cards.
 *
 * Out of scope (later PRs):
 *   - Streaming responses (PR 4.4)
 *   - Multi-turn / conversation history (PR 4.5)
 */

import { useCallback, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MessageSquare, Sparkles, RefreshCw, AlertTriangle, X } from 'lucide-react';
import {
  askCortexStreaming,
  type AnswerCitation,
} from '../api/ai';
import { ApiError } from '../api/client';

const MAX_QUERY_CHARS = 1000;

// ---------------------------------------------------------------------------
// Inline citation renderer
//
// The backend answer text contains markers like `[1]`, `[2]` that index into
// the citations array (1-based in text, 0-based in array). We render each
// marker as a chip <button> that navigates to the cited note. Anything
// between markers is rendered as plain text so paragraph breaks survive.
// ---------------------------------------------------------------------------

const _CITATION_RE = /\[(\d+)\]/g;

function renderAnswerWithChips(
  answer: string,
  citations: AnswerCitation[],
  onChipClick: (cite: AnswerCitation, oneIdx: number) => void,
): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  for (const m of answer.matchAll(_CITATION_RE)) {
    const start = m.index ?? 0;
    if (start > lastIndex) {
      out.push(<span key={`t-${key++}`}>{answer.slice(lastIndex, start)}</span>);
    }
    const oneIdx = Number(m[1]);
    const zeroIdx = oneIdx - 1;
    const cite = citations[zeroIdx];
    if (cite) {
      out.push(
        <button
          key={`c-${key++}`}
          type="button"
          aria-label={`Citation ${oneIdx}: ${cite.title}`}
          onClick={() => onChipClick(cite, oneIdx)}
          className="mx-0.5 inline-flex items-center rounded-full bg-indigo-600/30 px-1.5 py-0.5 text-xs font-semibold text-indigo-200 ring-1 ring-inset ring-indigo-500/40 transition-colors hover:bg-indigo-600/50 hover:text-white focus:outline-none focus:ring-2 focus:ring-indigo-300"
        >
          {oneIdx}
        </button>,
      );
    } else {
      // Citation index out of range — keep the raw marker so we don't
      // silently drop information.
      out.push(<span key={`r-${key++}`}>{m[0]}</span>);
    }
    lastIndex = start + m[0].length;
  }
  if (lastIndex < answer.length) {
    out.push(<span key={`t-${key++}`}>{answer.slice(lastIndex)}</span>);
  }
  return out;
}

// ---------------------------------------------------------------------------
// Error → friendly message
// ---------------------------------------------------------------------------

type ErrorView = { kind: 'rate' | 'server' | 'other'; message: string };

function describeError(err: unknown): ErrorView {
  if (err instanceof ApiError) {
    if (err.status === 429) {
      const sec = err.retryAfter ?? 60;
      const minutes = Math.max(1, Math.ceil(sec / 60));
      return {
        kind: 'rate',
        message: `You've used your hourly quota; try again in ${minutes} minute${minutes === 1 ? '' : 's'}.`,
      };
    }
    if (err.status >= 500) {
      return { kind: 'server', message: 'Cortex had trouble answering. Please try again.' };
    }
    return { kind: 'other', message: err.detail || 'Something went wrong.' };
  }
  return { kind: 'other', message: err instanceof Error ? err.message : 'Something went wrong.' };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AskPage(): React.ReactElement {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [inFlight, setInFlight] = useState(false);
  const [streamedAnswer, setStreamedAnswer] = useState('');
  const [citations, setCitations] = useState<AnswerCitation[]>([]);
  const [meta, setMeta] = useState<{ model: string; retrieval_count: number } | null>(null);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<ErrorView | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const trimmedLength = query.trim().length;
  const overLimit = query.length > MAX_QUERY_CHARS;
  const canSubmit = trimmedLength > 0 && !overLimit && !inFlight;
  const hasResult = done && streamedAnswer.length > 0;
  const hasPartial = inFlight && streamedAnswer.length > 0;

  const handleAsk = useCallback(async () => {
    if (!canSubmit) return;
    const q = query.trim();
    setInFlight(true);
    setError(null);
    setStreamedAnswer('');
    setCitations([]);
    setMeta(null);
    setElapsedMs(null);
    setDone(false);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    await askCortexStreaming(q, {
      signal: ctrl.signal,
      onMeta: (m) => setMeta({ model: m.model, retrieval_count: m.retrieval_count }),
      onToken: (t) => setStreamedAnswer((prev) => prev + t),
      onDone: (cits, ms) => {
        setCitations(cits);
        setElapsedMs(ms);
        setDone(true);
      },
      onError: (detail) => {
        // Mirror non-streaming describeError for rate-limit / server detail.
        const looksRate = /rate|quota|429/i.test(detail);
        if (looksRate) {
          setError(describeError(new ApiError(429, 'rate_limited', detail)));
        } else {
          setError(describeError(new ApiError(500, 'server_error', detail)));
        }
      },
    });
    setInFlight(false);
    abortRef.current = null;
  }, [canSubmit, query]);

  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setInFlight(false);
  }, []);

  const goToNote = useCallback(
    (noteId: string) => navigate(`/note/${noteId}`),
    [navigate],
  );

  const answerNodes = useMemo(() => {
    if (!streamedAnswer) return null;
    return renderAnswerWithChips(streamedAnswer, citations, (c) => goToNote(c.note_id));
  }, [streamedAnswer, citations, goToNote]);

  return (
    <div className="flex min-h-screen flex-col bg-[#0F172A] pb-24">
      {/* Header */}
      <header className="border-b border-slate-700 px-4 py-3">
        <h1 className="text-lg font-semibold text-slate-100">Ask Cortex</h1>
        <p className="text-xs text-slate-400">Ask any question about your notes.</p>
      </header>

      <main className="flex flex-1 flex-col gap-5 px-4 py-4">
        {/* Question form */}
        <section>
          <label htmlFor="ask-input" className="sr-only">
            Question
          </label>
          <textarea
            id="ask-input"
            aria-label="Question"
            placeholder="How do I think about leadership?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            rows={3}
            className="w-full resize-y rounded-xl border border-slate-700 bg-slate-900/60 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
          />
          <div className="mt-1 flex items-center justify-between text-xs">
            <span
              className={overLimit ? 'text-red-400' : 'text-slate-500'}
              data-testid="char-counter"
            >
              {query.length} / {MAX_QUERY_CHARS}
            </span>
            <button
              type="button"
              onClick={() => void handleAsk()}
              disabled={!canSubmit}
              className="flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {inFlight ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Thinking…
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" aria-hidden="true" />
                  Ask
                </>
              )}
            </button>
            {inFlight && (
              <button
                type="button"
                onClick={handleCancel}
                data-testid="cancel-button"
                aria-label="Cancel"
                className="ml-2 flex items-center gap-1 rounded-xl border border-slate-600 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-400"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
                Cancel
              </button>
            )}
          </div>
        </section>

        {/* Result panel */}
        <section aria-live="polite" className="flex flex-col gap-4">
          {inFlight && !hasPartial && (
            <div
              className="flex items-center gap-2 text-sm text-slate-400"
              data-testid="loading"
            >
              <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
              Thinking…
            </div>
          )}

          {!inFlight && !hasResult && !error && streamedAnswer.length === 0 && (
            <div
              className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-slate-700 px-4 py-10 text-center text-sm text-slate-500"
              data-testid="empty-state"
            >
              <MessageSquare className="h-6 w-6 text-slate-600" aria-hidden="true" />
              <p>Ask Cortex anything about your notes.</p>
            </div>
          )}

          {!inFlight && error && (
            <div
              className="flex flex-col gap-2 rounded-xl border border-red-500/40 bg-red-900/20 p-3"
              data-testid="error-panel"
            >
              <div className="flex items-start gap-2">
                <AlertTriangle
                  className="mt-0.5 h-4 w-4 shrink-0 text-red-300"
                  aria-hidden="true"
                />
                <p className="text-sm text-red-200">{error.message}</p>
              </div>
              {error.kind !== 'rate' && (
                <button
                  type="button"
                  onClick={() => void handleAsk()}
                  className="self-start rounded-md border border-red-400/50 px-2 py-1 text-xs font-medium text-red-100 hover:bg-red-800/30 focus:outline-none focus:ring-2 focus:ring-red-400"
                >
                  Retry
                </button>
              )}
            </div>
          )}

          {(hasResult || hasPartial) && !error && (
            <>
              <article
                className="rounded-xl border border-indigo-500/40 bg-slate-900/60 p-4"
                data-testid="answer-text"
              >
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-100">
                  {answerNodes}
                </p>
              </article>

              {done && citations.length > 0 && (
                <div className="flex flex-col gap-2" data-testid="citations">
                  <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Citations
                  </h2>
                  <ul className="flex flex-col gap-2">
                    {citations.map((c, i) => {
                      const oneIdx = i + 1;
                      const pct = Math.round(Math.max(0, Math.min(1, c.relevance)) * 100);
                      return (
                        <li key={`${c.note_id}-${i}`}>
                          <button
                            type="button"
                            data-testid={`citation-card-${oneIdx}`}
                            onClick={() => goToNote(c.note_id)}
                            className="flex w-full flex-col gap-1 rounded-xl border border-slate-700 bg-slate-800/50 p-3 text-left transition-colors hover:border-indigo-500/60 hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                          >
                            <div className="flex items-center gap-2">
                              <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-indigo-600/30 text-[11px] font-semibold text-indigo-200 ring-1 ring-inset ring-indigo-500/40">
                                {oneIdx}
                              </span>
                              <span className="flex-1 truncate text-sm font-medium text-slate-100">
                                {c.title || 'Untitled note'}
                              </span>
                              <span className="text-xs text-slate-400">{pct}%</span>
                            </div>
                            <p className="line-clamp-2 text-xs text-slate-400">{c.snippet}</p>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}

              {done && meta && (
                <p className="text-[11px] text-slate-500" data-testid="meta-footer">
                  Model: {meta.model} • Retrieved {meta.retrieval_count} notes
                  {elapsedMs !== null ? ` • ${elapsedMs}ms` : ''}
                </p>
              )}
            </>
          )}
        </section>
      </main>
    </div>
  );
}
