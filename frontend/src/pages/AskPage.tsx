/**
 * AskPage — Phase 4 / Round 16 / PR 4.5 (multi-turn follow-up).
 *
 * Conversational entry point. State is held entirely client-side (the API
 * Container App `maxReplicas=3` makes sticky in-memory infeasible — see
 * DECISIONS § 22ae). On each Ask we POST `/api/ai/answer` with the new
 * query plus a sliced `prior_messages` array (last 8 user/assistant turns)
 * so GPT-4o-mini can synthesise a follow-up grounded in the same retrieved
 * notes UI from PR 4.4. Conversation persists to `sessionStorage` so a
 * refresh doesn't lose context. "New conversation" clears it.
 *
 * Out of scope:
 *   - Server-side conversation persistence (deliberately client-only).
 *   - Retrieval-from-history (current query is still the only retrieval key).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MessageSquare,
  Sparkles,
  RefreshCw,
  AlertTriangle,
  X,
  Plus,
} from 'lucide-react';
import {
  askCortexStreaming,
  type AnswerCitation,
  type PriorMessage,
} from '../api/ai';
import { ApiError } from '../api/client';

const MAX_QUERY_CHARS = 1000;
const PRIOR_CAP = 8;
const STORAGE_KEY = 'cortex.ask.conversation';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ErrorView = { kind: 'rate' | 'server' | 'other'; message: string };

type UserTurn = { role: 'user'; content: string };

type AssistantTurn = {
  role: 'assistant';
  content: string;
  citations: AnswerCitation[];
  meta?: { model: string; retrieval_count: number };
  elapsedMs?: number;
  done: boolean;
  error?: ErrorView;
};

type Turn = UserTurn | AssistantTurn;

// ---------------------------------------------------------------------------
// Inline citation renderer (unchanged from PR 4.4)
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

function describeErrorDetail(detail: string): ErrorView {
  const looksRate = /rate|quota|429/i.test(detail);
  if (looksRate) return describeError(new ApiError(429, 'rate_limited', detail));
  return describeError(new ApiError(500, 'server_error', detail));
}

// ---------------------------------------------------------------------------
// sessionStorage helpers
// ---------------------------------------------------------------------------

function loadConversation(): Turn[] {
  if (typeof sessionStorage === 'undefined') return [];
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Turn[];
    if (!Array.isArray(parsed)) return [];
    return parsed.map((t) =>
      t.role === 'assistant' ? { ...t, done: true, citations: t.citations ?? [] } : t,
    );
  } catch {
    return [];
  }
}

function saveConversation(conv: Turn[]) {
  if (typeof sessionStorage === 'undefined') return;
  try {
    if (conv.length === 0) {
      sessionStorage.removeItem(STORAGE_KEY);
    } else {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(conv));
    }
  } catch {
    // quota / disabled → silently ignore
  }
}

function buildPriorMessages(conv: Turn[]): PriorMessage[] {
  const cleaned: PriorMessage[] = conv
    .filter((t) => {
      if (t.role === 'user') return t.content.trim().length > 0;
      return t.done && !t.error && t.content.trim().length > 0;
    })
    .map((t) => ({ role: t.role, content: t.content }));
  return cleaned.slice(-PRIOR_CAP);
}

// ---------------------------------------------------------------------------
// Sub-component: assistant turn body (answer + citations)
// ---------------------------------------------------------------------------

type AssistantTurnViewProps = {
  turn: AssistantTurn;
  onChipClick: (noteId: string) => void;
  onRetry?: () => void;
};

function AssistantTurnView({
  turn,
  onChipClick,
  onRetry,
}: AssistantTurnViewProps): React.ReactElement {
  const answerNodes = useMemo(() => {
    if (!turn.content) return null;
    return renderAnswerWithChips(turn.content, turn.citations, (c) => onChipClick(c.note_id));
  }, [turn.content, turn.citations, onChipClick]);

  if (turn.error) {
    return (
      <div
        className="flex flex-col gap-2 rounded-xl border border-red-500/40 bg-red-900/20 p-3"
        data-testid="error-panel"
      >
        <div className="flex items-start gap-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-300" aria-hidden="true" />
          <p className="text-sm text-red-200">{turn.error.message}</p>
        </div>
        {turn.error.kind !== 'rate' && onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="self-start rounded-md border border-red-400/50 px-2 py-1 text-xs font-medium text-red-100 hover:bg-red-800/30 focus:outline-none focus:ring-2 focus:ring-red-400"
          >
            Retry
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <article
        className="max-w-[85%] self-start rounded-2xl border border-indigo-500/40 bg-slate-900/60 p-4"
        data-testid="answer-text"
      >
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-100">
          {answerNodes}
        </p>
      </article>

      {turn.done && turn.citations.length > 0 && (
        <div className="flex flex-col gap-2" data-testid="citations">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Citations
          </h2>
          <ul className="flex flex-col gap-2">
            {turn.citations.map((c, i) => {
              const oneIdx = i + 1;
              const pct = Math.round(Math.max(0, Math.min(1, c.relevance)) * 100);
              return (
                <li key={`${c.note_id}-${i}`}>
                  <button
                    type="button"
                    data-testid={`citation-card-${oneIdx}`}
                    onClick={() => onChipClick(c.note_id)}
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

      {turn.done && turn.meta && (
        <p className="text-[11px] text-slate-500" data-testid="meta-footer">
          Model: {turn.meta.model} • Retrieved {turn.meta.retrieval_count} notes
          {turn.elapsedMs !== undefined ? ` • ${turn.elapsedMs}ms` : ''}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AskPage(): React.ReactElement {
  const navigate = useNavigate();
  const [conversation, setConversation] = useState<Turn[]>(() => loadConversation());
  const [query, setQuery] = useState('');
  const [inFlight, setInFlight] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    saveConversation(conversation);
  }, [conversation]);

  const trimmedLength = query.trim().length;
  const overLimit = query.length > MAX_QUERY_CHARS;
  const canSubmit = trimmedLength > 0 && !overLimit && !inFlight;

  const latestAssistantIndex = useMemo(() => {
    for (let i = conversation.length - 1; i >= 0; i--) {
      if (conversation[i].role === 'assistant') return i;
    }
    return -1;
  }, [conversation]);

  const latestAssistant =
    latestAssistantIndex >= 0
      ? (conversation[latestAssistantIndex] as AssistantTurn)
      : null;

  const showLoadingSpinner =
    inFlight && (!latestAssistant || latestAssistant.content.length === 0);

  const updateAssistantTurn = useCallback(
    (idx: number, patch: Partial<AssistantTurn>) => {
      setConversation((prev) => {
        const next = prev.slice();
        const cur = next[idx];
        if (!cur || cur.role !== 'assistant') return prev;
        next[idx] = { ...cur, ...patch };
        return next;
      });
    },
    [],
  );

  const runAsk = useCallback(
    async (q: string, prior: PriorMessage[], assistantIdx: number) => {
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setInFlight(true);

      await askCortexStreaming(q, {
        signal: ctrl.signal,
        prior_messages: prior,
        onMeta: (m) =>
          updateAssistantTurn(assistantIdx, {
            meta: { model: m.model, retrieval_count: m.retrieval_count },
          }),
        onToken: (t) =>
          setConversation((prev) => {
            const next = prev.slice();
            const cur = next[assistantIdx];
            if (!cur || cur.role !== 'assistant') return prev;
            next[assistantIdx] = { ...cur, content: cur.content + t };
            return next;
          }),
        onDone: (cits, ms) =>
          updateAssistantTurn(assistantIdx, {
            citations: cits,
            elapsedMs: ms,
            done: true,
          }),
        onError: (detail) =>
          updateAssistantTurn(assistantIdx, {
            error: describeErrorDetail(detail),
            done: true,
          }),
      });

      setInFlight(false);
      abortRef.current = null;
    },
    [updateAssistantTurn],
  );

  const handleAsk = useCallback(async () => {
    if (!canSubmit) return;
    const q = query.trim();
    const prior = buildPriorMessages(conversation);
    const assistantIdx = conversation.length + 1; // user appended at len, assistant at len+1

    setConversation((prev) => [
      ...prev,
      { role: 'user', content: q },
      { role: 'assistant', content: '', citations: [], done: false },
    ]);
    setQuery('');

    await runAsk(q, prior, assistantIdx);
  }, [canSubmit, conversation, query, runAsk]);

  const handleCancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setInFlight(false);
  }, []);

  const handleNewConversation = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setInFlight(false);
    setConversation([]);
    setQuery('');
    if (typeof sessionStorage !== 'undefined') {
      try {
        sessionStorage.removeItem(STORAGE_KEY);
      } catch {
        // ignore
      }
    }
  }, []);

  const handleRetryLatest = useCallback(() => {
    if (latestAssistantIndex < 1) return;
    const userTurn = conversation[latestAssistantIndex - 1];
    if (!userTurn || userTurn.role !== 'user') return;

    const priorBefore = buildPriorMessages(conversation.slice(0, latestAssistantIndex - 1));
    const idx = latestAssistantIndex;
    setConversation((prev) => {
      const next = prev.slice();
      next[idx] = { role: 'assistant', content: '', citations: [], done: false };
      return next;
    });
    void runAsk(userTurn.content, priorBefore, idx);
  }, [conversation, latestAssistantIndex, runAsk]);

  const goToNote = useCallback(
    (noteId: string) => navigate(`/note/${noteId}`),
    [navigate],
  );

  const isEmpty = conversation.length === 0;

  return (
    <div className="flex min-h-screen flex-col bg-[#0F172A] pb-24">
      <header className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-100">Ask Cortex</h1>
          <p className="text-xs text-slate-400">Ask any question about your notes.</p>
        </div>
        <button
          type="button"
          onClick={handleNewConversation}
          disabled={isEmpty && !inFlight}
          data-testid="new-conversation"
          className="flex items-center gap-1.5 rounded-xl border border-slate-600 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 transition-colors hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          New conversation
        </button>
      </header>

      <main className="flex flex-1 flex-col gap-5 px-4 py-4">
        <section aria-live="polite" className="flex flex-col gap-4">
          {isEmpty && !inFlight && (
            <div
              className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-slate-700 px-4 py-10 text-center text-sm text-slate-500"
              data-testid="empty-state"
            >
              <MessageSquare className="h-6 w-6 text-slate-600" aria-hidden="true" />
              <p>Ask Cortex anything about your notes.</p>
            </div>
          )}

          {conversation.map((turn, i) => {
            if (turn.role === 'user') {
              return (
                <div key={`u-${i}`} className="flex justify-end">
                  <div
                    data-testid="user-turn"
                    className="max-w-[80%] rounded-2xl bg-indigo-600 px-4 py-2 text-sm text-white shadow-sm"
                  >
                    <p className="whitespace-pre-wrap break-words">{turn.content}</p>
                  </div>
                </div>
              );
            }
            const isLatest = i === latestAssistantIndex;
            return (
              <div
                key={`a-${i}`}
                data-testid="assistant-turn"
                className="flex flex-col gap-2"
              >
                <AssistantTurnView
                  turn={turn}
                  onChipClick={goToNote}
                  onRetry={isLatest ? handleRetryLatest : undefined}
                />
              </div>
            );
          })}

          {showLoadingSpinner && (
            <div
              className="flex items-center gap-2 text-sm text-slate-400"
              data-testid="loading"
            >
              <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
              Thinking…
            </div>
          )}
        </section>

        <section className="mt-auto flex flex-col gap-2 rounded-xl border border-slate-700 bg-slate-900/40 p-3">
          <label htmlFor="ask-input" className="sr-only">
            Question
          </label>
          <textarea
            id="ask-input"
            aria-label="Question"
            placeholder={isEmpty ? 'How do I think about leadership?' : 'Ask a follow-up…'}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            rows={3}
            className="w-full resize-y rounded-xl border border-slate-700 bg-slate-900/60 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
          />
          <div className="flex items-center justify-between text-xs">
            <span
              className={overLimit ? 'text-red-400' : 'text-slate-500'}
              data-testid="char-counter"
            >
              {query.length} / {MAX_QUERY_CHARS}
            </span>
            <div className="flex items-center gap-2">
              {inFlight && (
                <button
                  type="button"
                  onClick={handleCancel}
                  data-testid="cancel-button"
                  aria-label="Cancel"
                  className="flex items-center gap-1 rounded-xl border border-slate-600 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-400"
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                  Cancel
                </button>
              )}
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
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
