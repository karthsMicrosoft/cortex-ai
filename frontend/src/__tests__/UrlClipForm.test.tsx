/**
 * Phase 5 / PR 5.3 — UrlClipForm tests (TDD red).
 *
 * UrlClipForm wraps `frontend/src/api/import.ts::importUrl()` in a small
 * compact form: URL input + "Save link" button + spinner overlay +
 * status-code → user-friendly error message mapping.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import React from 'react';

// --- API mock ---
vi.mock('../api/import', () => ({
  importUrl: vi.fn(),
}));

// ApiError must be importable from the same module path the component uses.
// The component throws/catches ApiError instances; we re-export the real one
// so `instanceof` checks pass.
import { ApiError } from '../api/client';
import { importUrl } from '../api/import';
import { UrlClipForm } from '../components/UrlClipForm';

beforeEach(() => {
  vi.clearAllMocks();
});

function renderForm(props: Partial<React.ComponentProps<typeof UrlClipForm>> = {}) {
  return render(<UrlClipForm {...props} />);
}

describe('UrlClipForm — render', () => {
  it('renders URL input and Save link button', () => {
    renderForm();
    const input = screen.getByLabelText(/url/i) as HTMLInputElement;
    expect(input).toBeInTheDocument();
    expect(input.type).toBe('url');
    expect(screen.getByRole('button', { name: /save link/i })).toBeInTheDocument();
  });

  it('renders with initialUrl prefilled', () => {
    renderForm({ initialUrl: 'https://example.com/x' });
    const input = screen.getByLabelText(/url/i) as HTMLInputElement;
    expect(input.value).toBe('https://example.com/x');
  });
});

describe('UrlClipForm — Save button enable/disable', () => {
  it('Save button is disabled when URL is empty', () => {
    renderForm();
    const btn = screen.getByRole('button', { name: /save link/i });
    expect(btn).toBeDisabled();
  });

  it('Save button is disabled for clearly invalid URL', () => {
    renderForm();
    const input = screen.getByLabelText(/url/i);
    fireEvent.change(input, { target: { value: 'not a url' } });
    expect(screen.getByRole('button', { name: /save link/i })).toBeDisabled();
  });

  it('Save button is enabled for a valid http(s) URL', () => {
    renderForm();
    const input = screen.getByLabelText(/url/i);
    fireEvent.change(input, { target: { value: 'https://example.com' } });
    expect(screen.getByRole('button', { name: /save link/i })).not.toBeDisabled();
  });
});

describe('UrlClipForm — submit flow', () => {
  it('clicking Save POSTs /api/import/url via importUrl()', async () => {
    vi.mocked(importUrl).mockResolvedValueOnce({ id: 'note-99' } as never);
    renderForm();
    fireEvent.change(screen.getByLabelText(/url/i), {
      target: { value: 'https://example.com/article' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save link/i }));

    await waitFor(() => {
      expect(importUrl).toHaveBeenCalledWith({ url: 'https://example.com/article' });
    });
  });

  it('loading state disables the Save button while in flight', async () => {
    let resolve!: (v: unknown) => void;
    vi.mocked(importUrl).mockReturnValueOnce(
      new Promise((r) => {
        resolve = r;
      }) as never,
    );
    renderForm();
    fireEvent.change(screen.getByLabelText(/url/i), {
      target: { value: 'https://example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save link/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save link|saving/i })).toBeDisabled();
    });
    expect(screen.getByRole('status')).toBeInTheDocument(); // spinner

    resolve({ id: 'x' });
  });

  it('successful save invokes onSuccess with the new note_id', async () => {
    vi.mocked(importUrl).mockResolvedValueOnce({ id: 'new-note-id' } as never);
    const onSuccess = vi.fn();
    renderForm({ onSuccess });
    fireEvent.change(screen.getByLabelText(/url/i), {
      target: { value: 'https://example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save link/i }));

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith('new-note-id');
    });
  });

  it('shows transient "Saved!" confirmation on success', async () => {
    vi.mocked(importUrl).mockResolvedValueOnce({ id: 'n' } as never);
    renderForm();
    fireEvent.change(screen.getByLabelText(/url/i), {
      target: { value: 'https://example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save link/i }));

    await waitFor(() => {
      expect(screen.getByText(/saved/i)).toBeInTheDocument();
    });
  });
});

describe('UrlClipForm — status-code → message mapping', () => {
  async function submitAndExpect(message: RegExp) {
    renderForm();
    fireEvent.change(screen.getByLabelText(/url/i), {
      target: { value: 'https://example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save link/i }));
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(message);
    });
  }

  it('400 shows "Invalid URL" message', async () => {
    vi.mocked(importUrl).mockRejectedValueOnce(new ApiError(400, 'bad', 'Bad URL'));
    await submitAndExpect(/invalid url/i);
  });

  it('403 shows internal-IPs message', async () => {
    vi.mocked(importUrl).mockRejectedValueOnce(new ApiError(403, 'forbidden', 'no'));
    await submitAndExpect(/internal ip/i);
  });

  it('413 shows too-large message', async () => {
    vi.mocked(importUrl).mockRejectedValueOnce(new ApiError(413, 'too_large', 'big'));
    await submitAndExpect(/too large|5\s?MB/i);
  });

  it('415 shows format-not-supported message', async () => {
    vi.mocked(importUrl).mockRejectedValueOnce(new ApiError(415, 'media', 'no'));
    await submitAndExpect(/format/i);
  });

  it('422 shows "No readable content" message', async () => {
    vi.mocked(importUrl).mockRejectedValueOnce(new ApiError(422, 'no_readable', 'x'));
    await submitAndExpect(/no readable content/i);
  });

  it('502 shows generic retry message', async () => {
    vi.mocked(importUrl).mockRejectedValueOnce(new ApiError(502, 'bad_gw', 'x'));
    await submitAndExpect(/couldn't fetch|try again later/i);
  });

  it('504 shows generic retry message', async () => {
    vi.mocked(importUrl).mockRejectedValueOnce(new ApiError(504, 'gw_to', 'x'));
    await submitAndExpect(/couldn't fetch|try again later/i);
  });

  it('falls back to error.message for unmapped statuses', async () => {
    vi.mocked(importUrl).mockRejectedValueOnce(new ApiError(500, 'oops', 'Server exploded'));
    await submitAndExpect(/server exploded|something went wrong/i);
  });

  it('after error, user can retry by clicking Save again', async () => {
    vi.mocked(importUrl)
      .mockRejectedValueOnce(new ApiError(502, 'gw', 'x'))
      .mockResolvedValueOnce({ id: 'n2' } as never);
    const onSuccess = vi.fn();
    renderForm({ onSuccess });
    fireEvent.change(screen.getByLabelText(/url/i), {
      target: { value: 'https://example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save link/i }));
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /save link/i }));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith('n2'));
  });
});

describe('UrlClipForm — onCancel', () => {
  it('clicking Cancel calls onCancel', () => {
    const onCancel = vi.fn();
    renderForm({ onCancel });
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalled();
  });

  it('does not render Cancel when onCancel is not provided', () => {
    renderForm();
    expect(screen.queryByRole('button', { name: /cancel/i })).toBeNull();
  });
});
