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

const { mockNavigate, mockAskCortex } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
  mockAskCortex: vi.fn(),
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
  askCortex: mockAskCortex,
}));

// We import the real ApiError from client (it's a class — no fetch involved
// at import time, so no extra mocks needed).
import { ApiError } from '../api/client';
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
    let resolve!: (v: typeof SAMPLE_ANSWER) => void;
    mockAskCortex.mockReturnValue(new Promise((r) => { resolve = r; }));
    renderPage();
    fireEvent.change(screen.getByRole('textbox', { name: /question/i }), {
      target: { value: 'hello?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^ask$/i }));

    expect(screen.getByRole('button', { name: /thinking|^ask$/i })).toBeDisabled();
    expect(screen.getByTestId('loading')).toBeInTheDocument();

    resolve(SAMPLE_ANSWER);
    await waitFor(() => {
      expect(mockAskCortex).toHaveBeenCalledWith('hello?');
    });
  });

  it('renders the answer text + citations on success', async () => {
    mockAskCortex.mockResolvedValue(SAMPLE_ANSWER);
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
    // Relevance shown as 0..100 percent
    expect(screen.getByText(/91%/)).toBeInTheDocument();
    expect(screen.getByText(/74%/)).toBeInTheDocument();
    // Footer with model + retrieval count + elapsed
    expect(screen.getByText(/gpt-4o-mini/i)).toBeInTheDocument();
    expect(screen.getByText(/2 notes/i)).toBeInTheDocument();
    expect(screen.getByText(/987\s*ms/i)).toBeInTheDocument();
  });

  it('renders inline [N] references as clickable chips (not raw [N] text)', async () => {
    mockAskCortex.mockResolvedValue(SAMPLE_ANSWER);
    renderPage();
    fireEvent.change(screen.getByRole('textbox', { name: /question/i }), {
      target: { value: 'q?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^ask$/i }));

    const ans = await screen.findByTestId('answer-text');
    // Raw "[1]" should NOT appear in the text content
    expect(ans.textContent).not.toMatch(/\[1\]/);
    expect(ans.textContent).not.toMatch(/\[2\]/);
    // Two chip buttons inside the answer
    const chips = screen.getAllByRole('button', { name: /citation 1|citation 2/i });
    expect(chips.length).toBe(2);
  });

  it('chip click navigates to /note/<citation note_id>', async () => {
    mockAskCortex.mockResolvedValue(SAMPLE_ANSWER);
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
    mockAskCortex.mockResolvedValue(SAMPLE_ANSWER);
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

  it('shows error message + retry on ApiError 5xx', async () => {
    mockAskCortex.mockRejectedValueOnce(new ApiError(500, 'server_error', 'boom'));
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

    // Retry triggers another askCortex call
    mockAskCortex.mockResolvedValueOnce(SAMPLE_ANSWER);
    fireEvent.click(retry);
    await waitFor(() => {
      expect(mockAskCortex).toHaveBeenCalledTimes(2);
    });
  });

  it('shows rate-limit message with Retry-After minutes on ApiError 429', async () => {
    const err = new ApiError(429, 'rate_limited', 'too many');
    (err as ApiError & { retryAfter?: number }).retryAfter = 180; // 3 minutes
    mockAskCortex.mockRejectedValueOnce(err);
    renderPage();
    fireEvent.change(screen.getByRole('textbox', { name: /question/i }), {
      target: { value: 'q?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^ask$/i }));

    await waitFor(() => {
      expect(screen.getByTestId('error-panel')).toBeInTheDocument();
    });
    expect(screen.getByText(/hourly quota/i)).toBeInTheDocument();
    expect(screen.getByText(/3 minute/i)).toBeInTheDocument();
  });
});
