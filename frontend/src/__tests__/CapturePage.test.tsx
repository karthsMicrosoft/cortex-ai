/**
 * Task 1.4 / 3.2 — CapturePage — TDD red
 *
 * Tests that `frontend/src/pages/CapturePage.tsx` renders:
 *   - <VoiceCapture /> FAB
 *   - Text input area for FR-1.4 manual capture
 *   - Image upload input for FR-1.5
 *   - Submitting text creates a LocalNote with sourceType='text'
 *   - Uploading an image creates a LocalNote with sourceType='image' and imageBlob
 *
 * Round 15 / PR #24 — Image capture polish: preview, resize, validation, save UX.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mock VoiceCapture (no top-level vars referenced in factory)
// ---------------------------------------------------------------------------

vi.mock('../components/VoiceCapture', () => ({
  VoiceCapture: ({ onNoteCreated }: { onNoteCreated?: (id: string) => void }) => (
    <button data-testid="voice-capture-fab" onClick={() => onNoteCreated?.('local-voice-id')}>
      Voice FAB
    </button>
  ),
}));

// ---------------------------------------------------------------------------
// Mock SyncIndicator (may be imported by CapturePage)
// ---------------------------------------------------------------------------

vi.mock('../components/SyncIndicator', () => ({
  SyncIndicator: () => <div data-testid="sync-indicator" />,
}));

// ---------------------------------------------------------------------------
// Mock db — use vi.fn() directly in factory (no top-level let vars)
// ---------------------------------------------------------------------------

vi.mock('../db', () => ({
  db: {
    notes: {
      add: vi.fn().mockResolvedValue('local-text-id'),
      update: vi.fn().mockResolvedValue(undefined),
    },
    syncQueue: {
      add: vi.fn().mockResolvedValue(1),
    },
  },
}));

// ---------------------------------------------------------------------------
// Mock uuid
// ---------------------------------------------------------------------------

vi.mock('uuid', () => ({
  v4: () => 'test-uuid',
}));

// ---------------------------------------------------------------------------
// Mock syncManager
// ---------------------------------------------------------------------------

vi.mock('../sync/syncManager', () => ({
  syncManager: {
    pushChanges: vi.fn().mockResolvedValue(undefined),
  },
}));

// ---------------------------------------------------------------------------
// Mock importUrl so the URL tab path is testable (Phase 5 / PR 5.3).
// ---------------------------------------------------------------------------

vi.mock('../api/import', () => ({
  importUrl: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Mock authStore (Zustand hook — called as useAuthStore(selector))
// Uses vi.hoisted so the factory can safely reference the value when the
// module is first imported (which now happens transitively via UrlClipForm
// → api/client → authStore).
// ---------------------------------------------------------------------------

const { _mockCaptureUseAuthStore } = vi.hoisted(() => {
  const state = { accessToken: 'test-token', user: null };
  return {
    _mockCaptureUseAuthStore: Object.assign(
      (selector: (s: typeof state) => unknown) => selector(state),
      { getState: () => state, subscribe: () => () => {}, setState: () => {} },
    ),
  };
});
vi.mock('../store/authStore', () => ({ useAuthStore: _mockCaptureUseAuthStore }));

// ---------------------------------------------------------------------------
// Import component under test
// ---------------------------------------------------------------------------

import { CapturePage } from '../pages/CapturePage';
import { Route, Routes } from 'react-router-dom';
import { importUrl } from '../api/import';

function renderCapturePage() {
  return render(
    <MemoryRouter>
      <CapturePage />
    </MemoryRouter>,
  );
}

function renderCapturePageWithRoutes() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<CapturePage />} />
        <Route path="/library" element={<div data-testid="library-page">Library</div>} />
        <Route path="/note/:id" element={<div data-testid="note-page">Note</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

// Helper to get the mocked db
async function getMockedDb() {
  const { db } = await import('../db');
  return db;
}

// ---------------------------------------------------------------------------
// Image / canvas globals for image capture flow (Round 15 / PR #24)
// ---------------------------------------------------------------------------
const _origCreateObjectURL = (typeof URL !== 'undefined' ? URL.createObjectURL : undefined) as
  | typeof URL.createObjectURL
  | undefined;
const _origRevokeObjectURL = (typeof URL !== 'undefined' ? URL.revokeObjectURL : undefined) as
  | typeof URL.revokeObjectURL
  | undefined;
const _origImage = (globalThis as { Image?: unknown }).Image;

class _FakeImage {
  public naturalWidth = 1024;
  public naturalHeight = 768;
  public width = 1024;
  public height = 768;
  public onload: (() => void) | null = null;
  public onerror: (() => void) | null = null;
  private _src = '';
  get src() { return this._src; }
  set src(v: string) {
    this._src = v;
    const w = (globalThis as unknown as { __nextImgWidth?: number }).__nextImgWidth;
    if (w) {
      this.naturalWidth = w;
      this.width = w;
    }
    setTimeout(() => this.onload?.(), 0);
  }
}

beforeEach(() => {
  // @ts-expect-error override for tests
  URL.createObjectURL = vi.fn((_b: Blob) => `blob:mock-${Math.random()}`);
  // @ts-expect-error override for tests
  URL.revokeObjectURL = vi.fn();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (HTMLCanvasElement.prototype as any).toBlob = function (
    cb: (blob: Blob | null) => void,
    type?: string,
  ) {
    cb(new Blob(['resized-bytes'], { type: type || 'image/jpeg' }));
  };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (HTMLCanvasElement.prototype as any).getContext = function () {
    return { drawImage: vi.fn() };
  };
  // @ts-expect-error override Image global for tests
  globalThis.Image = _FakeImage;
});

afterEach(() => {
  if (_origCreateObjectURL) URL.createObjectURL = _origCreateObjectURL;
  if (_origRevokeObjectURL) URL.revokeObjectURL = _origRevokeObjectURL;
  if (_origImage) (globalThis as unknown as { Image: unknown }).Image = _origImage;
  delete (globalThis as unknown as { __nextImgWidth?: number }).__nextImgWidth;
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CapturePage (Task 1.4 / 3.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --- Voice FAB ---

  it('renders VoiceCapture FAB', () => {
    renderCapturePage();
    expect(screen.getByTestId('voice-capture-fab')).toBeInTheDocument();
  });

  // --- Text capture (FR-1.4) ---

  it('renders a text area for manual capture', () => {
    renderCapturePage();
    const textarea = screen.getByRole('textbox');
    expect(textarea).toBeInTheDocument();
  });

  it('renders a submit button for text capture', () => {
    renderCapturePage();
    const btn = screen.getByRole('button', { name: /save|submit|capture/i });
    expect(btn).toBeInTheDocument();
  });

  it('submitting text creates a note with sourceType=text in IndexedDB', async () => {
    renderCapturePage();
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'My text note' } });

    const btn = screen.getByRole('button', { name: /save|submit|capture/i });
    fireEvent.click(btn);

    const db = await getMockedDb();
    await waitFor(() => expect(db.notes.add).toHaveBeenCalled());
    const arg = (db.notes.add as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(arg.sourceType).toBe('text');
    expect(arg.content).toBe('My text note');
  });

  it('text note is created with syncStatus=pending', async () => {
    renderCapturePage();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Hello' } });
    fireEvent.click(screen.getByRole('button', { name: /save|submit|capture/i }));

    const db = await getMockedDb();
    await waitFor(() => expect(db.notes.add).toHaveBeenCalled());
    const arg = (db.notes.add as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(arg.syncStatus).toBe('pending');
  });

  it('text note is queued in syncQueue', async () => {
    renderCapturePage();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Queue me' } });
    fireEvent.click(screen.getByRole('button', { name: /save|submit|capture/i }));

    const db = await getMockedDb();
    await waitFor(() => expect(db.syncQueue.add).toHaveBeenCalled());
    const q = (db.syncQueue.add as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(q.operation).toBe('create');
  });

  it('textarea is cleared after successful text capture', async () => {
    renderCapturePage();
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Clear me after save' } });
    fireEvent.click(screen.getByRole('button', { name: /save|submit|capture/i }));

    const db = await getMockedDb();
    await waitFor(() => expect(db.notes.add).toHaveBeenCalled());
    expect((textarea as HTMLTextAreaElement).value).toBe('');
  });

  // --- Image capture (FR-1.5) ---

  it('renders an image file input', () => {
    renderCapturePage();
    const input = screen.getByLabelText(/image|photo|upload/i) as HTMLInputElement;
    expect(input).toBeInTheDocument();
    expect(input.type).toBe('file');
  });

  it('uploading an image creates a note with sourceType=image', async () => {
    renderCapturePage();
    const fileInput = screen.getByLabelText(/image|photo|upload/i) as HTMLInputElement;
    const mockFile = new File(['img-data'], 'photo.jpg', { type: 'image/jpeg' });

    fireEvent.change(fileInput, { target: { files: [mockFile] } });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /save image/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: /save image/i }));

    const db = await getMockedDb();
    await waitFor(() => expect(db.notes.add).toHaveBeenCalled());
    const arg = (db.notes.add as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(arg.sourceType).toBe('image');
  });

  it('image note stores the imageBlob', async () => {
    renderCapturePage();
    const fileInput = screen.getByLabelText(/image|photo|upload/i) as HTMLInputElement;
    const mockFile = new File(['img-data'], 'photo.jpg', { type: 'image/jpeg' });

    fireEvent.change(fileInput, { target: { files: [mockFile] } });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /save image/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: /save image/i }));

    const db = await getMockedDb();
    await waitFor(() => expect(db.notes.add).toHaveBeenCalled());
    const arg = (db.notes.add as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(arg.imageBlob).toBeInstanceOf(Blob);
  });

  it('image note has syncStatus=pending', async () => {
    renderCapturePage();
    const fileInput = screen.getByLabelText(/image|photo|upload/i) as HTMLInputElement;
    fireEvent.change(fileInput, {
      target: { files: [new File(['d'], 'x.png', { type: 'image/png' })] },
    });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /save image/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: /save image/i }));

    const db = await getMockedDb();
    await waitFor(() => expect(db.notes.add).toHaveBeenCalled());
    const arg = (db.notes.add as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(arg.syncStatus).toBe('pending');
  });

  // --- Empty text submit does nothing ---

  it('does not create a note when text input is empty', async () => {
    renderCapturePage();
    fireEvent.click(screen.getByRole('button', { name: /save|submit|capture/i }));
    await new Promise((r) => setTimeout(r, 50));
    const db = await getMockedDb();
    expect(db.notes.add).not.toHaveBeenCalled();
  });

  // --- Round 15 / PR #24 — Image capture polish ---

  describe('Image capture polish (PR #24)', () => {
    it('selecting an image shows a preview', async () => {
      renderCapturePage();
      const fileInput = screen.getByLabelText(/image|photo|upload/i) as HTMLInputElement;
      const file = new File(['img'], 'a.png', { type: 'image/png' });
      fireEvent.change(fileInput, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByRole('img', { name: /preview|image/i })).toBeInTheDocument();
      });
      expect(URL.createObjectURL).toHaveBeenCalled();
    });

    it('image >5MB triggers resize (canvas.toBlob) before storing', async () => {
      renderCapturePage();
      const fileInput = screen.getByLabelText(/image|photo|upload/i) as HTMLInputElement;
      const big = new Blob([new Uint8Array(6 * 1024 * 1024)], { type: 'image/jpeg' });
      const file = new File([big], 'big.jpg', { type: 'image/jpeg' });
      Object.defineProperty(file, 'size', { value: 6 * 1024 * 1024 });
      const toBlobSpy = vi.spyOn(HTMLCanvasElement.prototype, 'toBlob');

      fireEvent.change(fileInput, { target: { files: [file] } });

      await waitFor(() => expect(toBlobSpy).toHaveBeenCalled());
    });

    it('image wider than 2048px triggers resize', async () => {
      (globalThis as unknown as { __nextImgWidth: number }).__nextImgWidth = 4096;
      renderCapturePage();
      const fileInput = screen.getByLabelText(/image|photo|upload/i) as HTMLInputElement;
      const file = new File(['x'], 'wide.jpg', { type: 'image/jpeg' });
      const toBlobSpy = vi.spyOn(HTMLCanvasElement.prototype, 'toBlob');

      fireEvent.change(fileInput, { target: { files: [file] } });

      await waitFor(() => expect(toBlobSpy).toHaveBeenCalled());
    });

    it('non-image file shows a validation error', async () => {
      renderCapturePage();
      const fileInput = screen.getByLabelText(/image|photo|upload/i) as HTMLInputElement;
      const file = new File(['hello'], 'a.txt', { type: 'text/plain' });
      fireEvent.change(fileInput, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText(/must be an image|invalid (file )?type|not an image/i)).toBeInTheDocument();
      });
      const db = await getMockedDb();
      expect(db.notes.add).not.toHaveBeenCalled();
    });

    it('clicking Save image note shows uploading state and stores the blob', async () => {
      renderCapturePage();
      const fileInput = screen.getByLabelText(/image|photo|upload/i) as HTMLInputElement;
      const file = new File(['x'], 'a.png', { type: 'image/png' });
      fireEvent.change(fileInput, { target: { files: [file] } });

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /save image/i })).toBeInTheDocument(),
      );

      const saveBtn = screen.getByRole('button', { name: /save image/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(screen.getByText(/uploading/i)).toBeInTheDocument();
      });

      const db = await getMockedDb();
      await waitFor(() => expect(db.notes.add).toHaveBeenCalled());
      const arg = (db.notes.add as ReturnType<typeof vi.fn>).mock.calls[0][0];
      expect(arg.sourceType).toBe('image');
      expect(arg.imageBlob).toBeInstanceOf(Blob);
    });

    it('Save failure shows error toast and keeps the preview', async () => {
      const db = await getMockedDb();
      (db.notes.add as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
        new Error('boom'),
      );

      renderCapturePage();
      const fileInput = screen.getByLabelText(/image|photo|upload/i) as HTMLInputElement;
      const file = new File(['x'], 'a.png', { type: 'image/png' });
      fireEvent.change(fileInput, { target: { files: [file] } });

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /save image/i })).toBeInTheDocument(),
      );
      fireEvent.click(screen.getByRole('button', { name: /save image/i }));

      await waitFor(() => {
        expect(screen.getByText(/failed|error|try again/i)).toBeInTheDocument();
      });
      expect(screen.getByRole('img', { name: /preview|image/i })).toBeInTheDocument();
    });

    it('Cancel/Remove revokes the object URL', async () => {
      renderCapturePage();
      const fileInput = screen.getByLabelText(/image|photo|upload/i) as HTMLInputElement;
      const file = new File(['x'], 'a.png', { type: 'image/png' });
      fireEvent.change(fileInput, { target: { files: [file] } });

      await waitFor(() =>
        expect(screen.getByRole('img', { name: /preview|image/i })).toBeInTheDocument(),
      );

      const removeBtn =
        screen.queryByRole('button', { name: /remove|clear|×/i }) ||
        screen.getByRole('button', { name: /cancel/i });
      fireEvent.click(removeBtn);

      await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalled());
    });
  });

  // -----------------------------------------------------------------------
  // Phase 5 / PR 5.3 — URL tab + Clip-from-URL form
  // -----------------------------------------------------------------------
  describe('URL tab (PR 5.3)', () => {
    it('renders a URL tab control', () => {
      renderCapturePage();
      expect(screen.getByRole('button', { name: /^url$/i })).toBeInTheDocument();
    });

    it('renders Text, Voice, Image, URL tab controls', () => {
      renderCapturePage();
      expect(screen.getByRole('button', { name: /^text$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^voice$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^image$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^url$/i })).toBeInTheDocument();
    });

    it('clicking URL tab shows the UrlClipForm (URL input + Save link button)', () => {
      renderCapturePage();
      fireEvent.click(screen.getByRole('button', { name: /^url$/i }));
      expect(screen.getByLabelText(/url/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /save link/i })).toBeInTheDocument();
    });

    it('clicking another tab hides the UrlClipForm', () => {
      renderCapturePage();
      fireEvent.click(screen.getByRole('button', { name: /^url$/i }));
      expect(screen.getByRole('button', { name: /save link/i })).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /^text$/i }));
      expect(screen.queryByRole('button', { name: /save link/i })).toBeNull();
    });

    it('successful URL clip navigates to /note/:id', async () => {
      vi.mocked(importUrl).mockResolvedValueOnce({ id: 'note-clip-1' } as never);
      renderCapturePageWithRoutes();
      fireEvent.click(screen.getByRole('button', { name: /^url$/i }));

      const urlInput = screen.getByLabelText(/url/i);
      fireEvent.change(urlInput, { target: { value: 'https://example.com/article' } });
      fireEvent.click(screen.getByRole('button', { name: /save link/i }));

      await waitFor(() => {
        expect(screen.getByTestId('note-page')).toBeInTheDocument();
      });
    });
  });
});
