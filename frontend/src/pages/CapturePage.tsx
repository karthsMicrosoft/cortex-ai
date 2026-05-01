import { useCallback, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { v4 as uuidv4 } from 'uuid';
import { Image, Send } from 'lucide-react';
import { db } from '../db';
import type { LocalNote } from '../db';
import { VoiceCapture } from '../components/VoiceCapture';
import { SyncIndicator } from '../components/SyncIndicator';
import { syncManager } from '../sync/syncManager';

// ---------------------------------------------------------------------------
// CapturePage
// ---------------------------------------------------------------------------

/**
 * CapturePage — the home/capture surface.
 *
 * Provides:
 *  1. Text input area (FR-1.4 manual capture)
 *  2. Image upload input (FR-1.5)
 *  3. VoiceCapture FAB (voice recording)
 */
export function CapturePage(): React.ReactElement {
  const navigate = useNavigate();
  const [textContent, setTextContent] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ---------------------------------------------------------------------- text capture

  const handleTextSubmit = useCallback(async () => {
    const content = textContent.trim();
    if (!content) return;

    setIsSubmitting(true);
    const localId = uuidv4();
    const now = new Date();

    const localNote: LocalNote = {
      localId,
      content,
      sourceType: 'text',
      category: 'Ideas',
      tags: [],
      syncStatus: 'pending',
      processingStatus: 'raw',
      createdAt: now,
      updatedAt: now,
    };

    await db.notes.add(localNote);
    await db.syncQueue.add({
      operation: 'create',
      entityType: 'note',
      entityId: localId,
      payload: { localId },
      timestamp: now,
      retryCount: 0,
    });

    setTextContent('');
    setIsSubmitting(false);
    // 2026-05-01 fix: nudge a sync push immediately so the note flips from
    // 'pending' to 'synced' without waiting for the 30s polling tick.
    void syncManager.pushChanges();
    navigate('/library');
  }, [textContent, navigate]);

  // ---------------------------------------------------------------------- image capture (FR-1.5)

  const handleImageFile = useCallback(async (file: File) => {
    const localId = uuidv4();
    const now = new Date();
    const imageBlob = file;

    const localNote: LocalNote = {
      localId,
      content: '',
      sourceType: 'image',
      category: 'Ideas',
      imageBlob,
      tags: [],
      syncStatus: 'pending',
      processingStatus: 'raw',
      createdAt: now,
      updatedAt: now,
    };

    await db.notes.add(localNote);
    await db.syncQueue.add({
      operation: 'create',
      entityType: 'note',
      entityId: localId,
      payload: { localId },
      timestamp: now,
      retryCount: 0,
    });

    // 2026-05-01 fix: nudge a sync push immediately so image notes don't
    // sit in 'pending' until the 30s polling tick.
    void syncManager.pushChanges();
    navigate('/library');
  }, [navigate]);

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) void handleImageFile(file);
    },
    [handleImageFile],
  );

  // ---------------------------------------------------------------------- render

  return (
    <div className="flex min-h-screen flex-col bg-[#0F172A] pb-24">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
        <h1 className="text-lg font-semibold text-slate-100">Capture</h1>
        <SyncIndicator />
      </header>

      {/* Body */}
      <main className="flex flex-1 flex-col gap-4 px-4 py-6">
        {/* Text area */}
        <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-4">
          <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-400">
            Quick Note
          </label>
          <textarea
            className="w-full resize-none rounded-lg border border-slate-600 bg-slate-900 p-3 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            rows={5}
            placeholder="What's on your mind?"
            value={textContent}
            onChange={(e) => setTextContent(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                void handleTextSubmit();
              }
            }}
          />
          <div className="mt-3 flex items-center justify-between">
            {/* Image upload — label wraps visually-styled button + hidden input */}
            <label
              htmlFor="image-upload-input"
              className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-slate-400 hover:border-slate-500 hover:text-slate-200"
            >
              <Image className="h-4 w-4" aria-hidden="true" />
              Upload image
            </label>
            <input
              id="image-upload-input"
              ref={fileInputRef}
              type="file"
              accept="image/*"
              aria-label="Upload image"
              className="sr-only"
              onChange={handleFileChange}
            />

            {/* Submit text note */}
            <button
              type="button"
              onClick={() => void handleTextSubmit()}
              disabled={!textContent.trim() || isSubmitting}
              className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:opacity-50"
            >
              <Send className="h-4 w-4" aria-hidden="true" />
              Save
            </button>
          </div>
        </div>

        {/* Hint */}
        <p className="text-center text-xs text-slate-500">
          Or hold the mic button below to record a voice note.
        </p>
      </main>

      {/* FAB */}
      <VoiceCapture onNoteCreated={() => navigate('/library')} />
    </div>
  );
}

export default CapturePage;
