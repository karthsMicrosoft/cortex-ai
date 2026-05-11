/**
 * AskPage.test.tsx — Phase 4 / Round 16 / PR 4.2 (Ask UI)
 *
 * TDD red-phase tests for frontend/src/pages/AskPage.tsx.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks (hoisted)
// ---------------------------------------------------------------------------

const { mockNavigate, mockAskCortexStreaming } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
  mockAskCortexStreaming: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  );
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../api/ai', () => ({
  askCortexStreaming: mockAskCortexStreaming,
}));

import AskPage from '../pages/AskPage';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderPage() {
  return render(
    <MemoryRouter>
      <AskPage />
    </MemoryRouter>,
  );
}

const SAMPLE_ANSWER = {
  answer: 'Leadership is service [1]. Trust matters [2].',
  citations: [
    { note_id: 'note-aaa', title: 'On leadership', snippet: 'lead by example', relevance: 0.91 },
    { note_id: 'note-bbb', title: 'On trust', snippet: 'trust compounds', relevance: 0.74 },
  ],
  model: 'gpt-4o-mini',
  retrieval_count: 2,
  elapsed_ms: 987,
};

/** Drive askCortexStreaming via its callbacks: meta → tokens → done. */
function streamWholeAnswer() {
  mockAskCortexStreaming.mockImplementation(async (_q: string, opts: {
    onMeta?: (m: { type: 'meta'; retrieval_count: number; model: string }) => void;
    onToken?: (t: string) => void;
    onDone?: (cits: typeof SAMPLE_ANSWER.citations, ms: number) => void;
  }) => {
    opts.onMeta?.({ type: 'meta', retrieval_count: SAMPLE_ANSWER.retrieval_count, model: SAMPLE_ANSWER.model });
    opts.onToken?.(SAMPLE_ANSWER.answer);
    opts.onDone?.(SAMPLE_ANSWER.citations, SAMPLE_ANSWER.elapsed_ms);
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AskPage — render', () => {
  it('renders Ask Cortex heading and textarea', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: /ask cortex/i })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /question/i })).toBeInTheDocument();
  });

  it('shows the empty state before any query', () => {
    renderPage();
    expect(screen.getByText(/ask cortex anything about your notes/i)).toBeInTheDocument();
  });

  it('Ask button is disabled when query is empty', () => {
    renderPage();
    expect(screen.getByRole('button', { name: /^ask$/i })).toBeDisabled();
  });

  it('char counter updates as user types', () => {
    renderPage();
    const ta = screen.getByRole('textbox', { name: /question/i });
    fireEvent.change(ta, { target: { value: 'hi' } });
    expect(screen.getByText(/2\s*\/\s*1000/i)).toBeInTheDocument();
  });

  it('Ask button is disabled when query exceeds 1000 chars', () => {
    renderPage();
    const ta = screen.getByRole('textbox', { name: /question/i });
    fireEvent.change(ta, { target: { value: 'x'.repeat(1001) } });
    expect(screen.getByRole('button', { name: /^ask$/i })).toBeDisabled();
  });
});

describe('AskPage — flow', () => {
  it('Ask button is disabled while in flight', async () => {
    let resolve!: () => void;
    mockAskCortexStreaming.mockImplementation(() => new Promise<void>((r) => { resolve = r; }));
    renderPage();
    fireEvent.change(screen.getByRole('textbox', { name: /question/i }), {
      target: { value: 'hello?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^ask$/i }));

    expect(screen.getByRole('button', { name: /thinking|^ask$/i })).toBeDisabled();
    expect(screen.getByTestId('loading')).toBeInTheDocument();

    resolve();
    await waitFor(() => {
      expect(mockAskCortexStreaming).toHaveBeenCalled();
      expect(mockAskCortexStreaming.mock.calls[0][0]).toBe('hello?');
    });
  });

  it('renders the answer text + citations on success', async () => {
    streamWholeAnswer();
    renderPage();
    fireEvent.change(screen.getByRole('textbox', { name: /question/i }), {
      target: { value: 'hello?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^ask$/i }));

    await waitFor(() => {
      expect(screen.getByTestId('answer-text')).toBeInTheDocument();
    });
    expect(screen.getByText(/on leadership/i)).toBeInTheDocument();
    expect(screen.getByText(/on trust/i)).toBeInTheDocument();
    expect(screen.getByText(/91%/)).toBeInTheDocument();
    expect(screen.getByText(/74%/)).toBeInTheDocument();
    expect(screen.getByText(/gpt-4o-mini/i)).toBeInTheDocument();
    expect(screen.getByText(/2 notes/i)).toBeInTheDocument();
    expect(screen.getByText(/987\s*ms/i)).toBeInTheDocument();
  });

  it('renders inline [N] references as clickable chips (not raw [N] text)', async () => {
    streamWholeAnswer();
    renderPage();
    fireEvent.change(screen.getByRole('textbox', { name: /question/i }), {
      target: { value: 'q?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^ask$/i }));

    const ans = await screen.findByTestId('answer-text');
    expect(ans.textContent).not.toMatch(/\[1\]/);
    expect(ans.textContent).not.toMatch(/\[2\]/);
    const chips = screen.getAllByRole('button', { name: /citation 1|citation 2/i });
    expect(chips.length).toBe(2);
  });

  it('chip click navigates to /note/<citation note_id>', async () => {
    streamWholeAnswer();
    renderPage();
    fireEvent.change(screen.getByRole('textbox', { name: /question/i }), {
      target: { value: 'q?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^ask$/i }));

    await screen.findByTestId('answer-text');
    const chip1 = screen.getByRole('button', { name: /citation 1/i });
    fireEvent.click(chip1);
    expect(mockNavigate).toHaveBeenCalledWith('/note/note-aaa');
  });

  it('citation card click navigates to /note/<note_id>', async () => {
    streamWholeAnswer();
    renderPage();
    fireEvent.change(screen.getByRole('textbox', { name: /question/i }), {
      target: { value: 'q?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^ask$/i }));

    await screen.findByTestId('answer-text');
    const card2 = screen.getByTestId('citation-card-2');
    fireEvent.click(card2);
    expect(mockNavigate).toHaveBeenCalledWith('/note/note-bbb');
  });

  it('shows error message + retry on stream error (5xx-like)', async () => {
    mockAskCortexStreaming.mockImplementationOnce(async (_q, opts: { onError?: (d: string) => void }) => {
      opts.onError?.('Upstream LLM failed: RuntimeError');
    });
    renderPage();
    fireEvent.change(screen.getByRole('textbox', { name: /question/i }), {
      target: { value: 'q?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^ask$/i }));

    await waitFor(() => {
      expect(screen.getByTestId('error-panel')).toBeInTheDocument();
    });
    const retry = screen.getByRole('button', { name: /retry/i });
    expect(retry).toBeInTheDocument();

    streamWholeAnswer();
    fireEvent.click(retry);
    await waitFor(() => {
      expect(mockAskCortexStreaming).toHaveBeenCalledTimes(2);
    });
  });

  it('shows rate-limit message when error detail mentions rate/quota', async () => {
    mockAskCortexStreaming.mockImplementationOnce(async (_q, opts: { onError?: (d: string) => void }) => {
      opts.onError?.('rate limited (429)');
    });
    renderPage();
    fireEvent.change(screen.getByRole('textbox', { name: /question/i }), {
      target: { value: 'q?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^ask$/i }));

    await waitFor(() => {
      expect(screen.getByTestId('error-panel')).toBeInTheDocument();
    });
    expect(screen.getByText(/hourly quota/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// PR 4.4 — streaming behaviour
// ---------------------------------------------------------------------------

describe('AskPage — streaming (PR 4.4)', () => {
  it('tokens render progressively as they arrive', async () => {
    let push: ((t: string) => void) | null = null;
    let finish: (() => void) | null = null;
    mockAskCortexStreaming.mockImplementation(async (_q, opts: {
      onMeta?: (m: { type: 'meta'; retrieval_count: number; model: string }) => void;
      onToken?: (t: string) => void;
      onDone?: (cits: typeof SAMPLE_ANSWER.citations, ms: number) => void;
    }) => {
      opts.onMeta?.({ type: 'meta', retrieval_count: 1, model: 'gpt-4o-mini' });
      push = (t: string) => opts.onToken?.(t);
      await new Promise<void>((r) => {
        finish = () => {
          opts.onDone?.([], 100);
          r();
        };
      });
    });
    renderPage();
    fireEvent.change(screen.getByRole('textbox', { name: /question/i }), { target: { value: 'q' } });
    fireEvent.click(screen.getByRole('button', { name: /^ask$/i }));

    await waitFor(() => expect(push).not.toBeNull());
    push!('Hello');
    await waitFor(() => {
      expect(screen.getByTestId('answer-text').textContent).toMatch(/Hello/);
    });
    push!(' world');
    await waitFor(() => {
      expect(screen.getByTestId('answer-text').textContent).toMatch(/Hello world/);
    });
    finish!();
  });

  it('citations only appear after done frame', async () => {
    let push: ((t: string) => void) | null = null;
    let done: (() => void) | null = null;
    mockAskCortexStreaming.mockImplementation(async (_q, opts: {
      onMeta?: (m: { type: 'meta'; retrieval_count: number; model: string }) => void;
      onToken?: (t: string) => void;
      onDone?: (cits: typeof SAMPLE_ANSWER.citations, ms: number) => void;
    }) => {
      opts.onMeta?.({ type: 'meta', retrieval_count: 2, model: 'gpt-4o-mini' });
      push = (t: string) => opts.onToken?.(t);
      await new Promise<void>((r) => {
        done = () => {
          opts.onDone?.(SAMPLE_ANSWER.citations, 500);
          r();
        };
      });
    });
    renderPage();
    fireEvent.change(screen.getByRole('textbox', { name: /question/i }), { target: { value: 'q' } });
    fireEvent.click(screen.getByRole('button', { name: /^ask$/i }));

    await waitFor(() => expect(push).not.toBeNull());
    push!('streaming…');
    await waitFor(() => {
      expect(screen.getByTestId('answer-text')).toBeInTheDocument();
    });
    // Citations are NOT yet rendered.
    expect(screen.queryByTestId('citations')).not.toBeInTheDocument();

    done!();
    await waitFor(() => {
      expect(screen.getByTestId('citations')).toBeInTheDocument();
    });
    expect(screen.getByText(/on leadership/i)).toBeInTheDocument();
  });

  it('cancel button aborts the in-flight stream', async () => {
    let receivedSignal: AbortSignal | undefined;
    let release!: () => void;
    mockAskCortexStreaming.mockImplementation(async (_q, opts: { signal?: AbortSignal }) => {
      receivedSignal = opts.signal;
      await new Promise<void>((r) => { release = r; });
    });
    renderPage();
    fireEvent.change(screen.getByRole('textbox', { name: /question/i }), { target: { value: 'q' } });
    fireEvent.click(screen.getByRole('button', { name: /^ask$/i }));

    const cancel = await screen.findByTestId('cancel-button');
    fireEvent.click(cancel);
    expect(receivedSignal?.aborted).toBe(true);
    release();
  });
});
