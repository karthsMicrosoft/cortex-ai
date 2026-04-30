/**
 * Task 1.4 / 3.2 — CapturePage — TDD red
 *
 * Tests that `frontend/src/pages/CapturePage.tsx` renders:
 *   - <VoiceCapture /> FAB
 *   - Text input area for FR-1.4 manual capture
 *   - Image upload input for FR-1.5
 *   - Submitting text creates a LocalNote with sourceType='text'
 *   - Uploading an image creates a LocalNote with sourceType='image' and imageBlob
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
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
// Mock authStore (Zustand hook — called as useAuthStore(selector))
// ---------------------------------------------------------------------------

const _mockCaptureAuthState = { accessToken: 'test-token', user: null };
const _mockCaptureUseAuthStore = Object.assign(
  (selector: (s: typeof _mockCaptureAuthState) => unknown) => selector(_mockCaptureAuthState),
  { getState: () => _mockCaptureAuthState, subscribe: vi.fn(), setState: vi.fn() },
);
vi.mock('../store/authStore', () => ({ useAuthStore: _mockCaptureUseAuthStore }));

// ---------------------------------------------------------------------------
// Import component under test
// ---------------------------------------------------------------------------

import { CapturePage } from '../pages/CapturePage';

function renderCapturePage() {
  return render(
    <MemoryRouter>
      <CapturePage />
    </MemoryRouter>,
  );
}

// Helper to get the mocked db
async function getMockedDb() {
  const { db } = await import('../db');
  return db;
}

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
});
