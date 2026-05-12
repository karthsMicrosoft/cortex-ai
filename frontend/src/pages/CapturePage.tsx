import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { v4 as uuidv4 } from 'uuid';
import { Image as ImageIcon, Send, Loader2, Mic, Type, Link as LinkIcon } from 'lucide-react';
import { db } from '../db';
import type { LocalNote } from '../db';
import { VoiceCapture } from '../components/VoiceCapture';
import { SyncIndicator } from '../components/SyncIndicator';
import { ImagePreview } from '../components/ImagePreview';
import { UrlClipForm } from '../components/UrlClipForm';
import { syncManager } from '../sync/syncManager';

// ---------------------------------------------------------------------------
// Image-resize constants (Round 15 / PR #24)
// ---------------------------------------------------------------------------

const MAX_IMAGE_BYTES = 5 * 1024 * 1024; // 5 MB → resize threshold
const MAX_IMAGE_WIDTH = 2048; // px → resize threshold
const RESIZE_QUALITY = 0.85;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Load an image File/Blob and return its decoded HTMLImageElement.
 */
function loadImage(blob: Blob): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('Failed to decode image'));
    };
    img.src = url;
  });
}

/**
 * Downscale `blob` so its width is at most MAX_IMAGE_WIDTH, preserving
 * aspect ratio, re-encoded as JPEG @ RESIZE_QUALITY. Returns the original
 * blob unchanged if a canvas can't be obtained.
 */
async function resizeImage(blob: Blob): Promise<Blob> {
  const img = await loadImage(blob);
  const targetWidth = Math.min(img.naturalWidth || img.width, MAX_IMAGE_WIDTH);
  const ratio = targetWidth / (img.naturalWidth || img.width || targetWidth);
  const targetHeight = Math.round((img.naturalHeight || img.height) * ratio);

  const canvas = document.createElement('canvas');
  canvas.width = targetWidth;
  canvas.height = targetHeight;
  const ctx = canvas.getContext('2d');
  if (!ctx) return blob;
  ctx.drawImage(img, 0, 0, targetWidth, targetHeight);

  return new Promise<Blob>((resolve) => {
    canvas.toBlob(
      (out) => resolve(out ?? blob),
      'image/jpeg',
      RESIZE_QUALITY,
    );
  });
}

// ---------------------------------------------------------------------------
// CapturePage
// ---------------------------------------------------------------------------

/**
 * CapturePage — the home/capture surface.
 *
 * Provides:
 *  1. Text input area (FR-1.4 manual capture)
 *  2. Image upload input (FR-1.5) with preview, client-side resize, and
 *     explicit Save / Cancel controls (Round 15 / PR #24).
 *  3. VoiceCapture FAB (voice recording)
 */
export function CapturePage(): React.ReactElement {
  const navigate = useNavigate();
  const [textContent, setTextContent] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ---------------------------------------------------------------------- tab state (PR 5.3)
  type CaptureTab = 'text' | 'voice' | 'image' | 'url';
  const [activeTab, setActiveTab] = useState<CaptureTab>('text');

  // ---------------------------------------------------------------------- image-flow state

  const [imageBlob, setImageBlob] = useState<Blob | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Always revoke any object URL we own when it changes or on unmount.
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

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
    void syncManager.pushChanges();
    navigate('/library');
  }, [textContent, navigate]);

  // ---------------------------------------------------------------------- image capture (FR-1.5)

  const clearImage = useCallback(() => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setImageBlob(null);
    setImageError(null);
    setUploadError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [previewUrl]);

  const handleFileChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      setUploadError(null);

      // 1. Validate content type
      if (!file.type || !file.type.startsWith('image/')) {
        setImageError('Selected file must be an image.');
        if (fileInputRef.current) fileInputRef.current.value = '';
        return;
      }
      setImageError(null);

      // 2. Resize if oversized (>5MB) or too wide (>2048px)
      let finalBlob: Blob = file;
      try {
        if (file.size > MAX_IMAGE_BYTES) {
          finalBlob = await resizeImage(file);
        } else {
          // Probe width first; only resize if needed
          const probe = await loadImage(file);
          if ((probe.naturalWidth || probe.width) > MAX_IMAGE_WIDTH) {
            finalBlob = await resizeImage(file);
          }
        }
      } catch {
        setImageError('Could not read this image file.');
        if (fileInputRef.current) fileInputRef.current.value = '';
        return;
      }

      // 3. Build preview URL (revoking any previous one)
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setImageBlob(finalBlob);
      setPreviewUrl(URL.createObjectURL(finalBlob));
    },
    [previewUrl],
  );

  const handleImageSave = useCallback(async () => {
    if (!imageBlob) return;
    setIsUploading(true);
    setUploadError(null);

    const localId = uuidv4();
    const now = new Date();
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

    try {
      await db.notes.add(localNote);
      await db.syncQueue.add({
        operation: 'create',
        entityType: 'note',
        entityId: localId,
        payload: { localId },
        timestamp: now,
        retryCount: 0,
      });
      void syncManager.pushChanges();
      // Revoke before navigating away
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
      setImageBlob(null);
      setIsUploading(false);
      navigate('/library');
    } catch (err) {
      // Keep the preview so the user can retry
      setIsUploading(false);
      setUploadError(
        err instanceof Error
          ? `Failed to save image note: ${err.message}. Try again.`
          : 'Failed to save image note. Try again.',
      );
    }
  }, [imageBlob, previewUrl, navigate]);

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
        {/* Capture-mode tabs (PR 5.3) */}
        <div
          aria-label="Capture mode"
          className="flex flex-wrap items-center gap-2"
        >
          {(
            [
              { id: 'text', label: 'Text', Icon: Type },
              { id: 'voice', label: 'Voice', Icon: Mic },
              { id: 'image', label: 'Image', Icon: ImageIcon },
              { id: 'url', label: 'URL', Icon: LinkIcon },
            ] as const
          ).map(({ id, label, Icon }) => {
            const active = activeTab === id;
            return (
              <button
                key={id}
                type="button"
                aria-pressed={active}
                onClick={() => setActiveTab(id)}
                className={
                  'flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-colors ' +
                  (active
                    ? 'border-indigo-500 bg-indigo-600 text-white'
                    : 'border-slate-600 bg-slate-800/40 text-slate-300 hover:border-slate-500 hover:text-slate-100')
                }
              >
                <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                {label}
              </button>
            );
          })}
        </div>

        {/* URL tab — Clip-from-URL form (PR 5.3) */}
        {activeTab === 'url' ? (
          <UrlClipForm
            onSuccess={(noteId) =>
              navigate(`/note/${encodeURIComponent(noteId)}`)
            }
          />
        ) : null}

        {/* Voice tab — hint; the FAB stays mounted at the bottom */}
        {activeTab === 'voice' ? (
          <p className="rounded-xl border border-slate-700 bg-slate-800/60 p-4 text-center text-sm text-slate-300">
            Hold the mic button below to record a voice note.
          </p>
        ) : null}

        {/* Text + Image tabs share the legacy capture surface (text area +
            image upload control) so existing workflows keep working. */}
        {activeTab !== 'url' && activeTab !== 'voice' ? (
          <>
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
              <ImageIcon className="h-4 w-4" aria-hidden="true" />
              Upload image
            </label>
            <input
              id="image-upload-input"
              ref={fileInputRef}
              type="file"
              accept="image/*"
              aria-label="Upload image"
              className="sr-only"
              onChange={(e) => void handleFileChange(e)}
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

          {/* Inline image-validation error */}
          {imageError ? (
            <p
              role="alert"
              className="mt-3 rounded-md border border-red-700/40 bg-red-900/30 p-2 text-sm text-red-200"
            >
              {imageError}
            </p>
          ) : null}
        </div>

        {/* Image preview + Save / Cancel controls */}
        {previewUrl ? (
          <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-4">
            <ImagePreview
              src={previewUrl}
              alt="Image preview"
              onRemove={clearImage}
            />

            {uploadError ? (
              <p
                role="alert"
                className="mt-3 rounded-md border border-red-700/40 bg-red-900/30 p-2 text-sm text-red-200"
              >
                {uploadError}
              </p>
            ) : null}

            <div className="mt-3 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={clearImage}
                disabled={isUploading}
                className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-slate-300 hover:border-slate-500 hover:text-slate-100 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleImageSave()}
                disabled={isUploading}
                className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:opacity-50"
              >
                {isUploading ? (
                  <>
                    <Loader2
                      className="h-4 w-4 animate-spin"
                      aria-hidden="true"
                    />
                    Uploading…
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4" aria-hidden="true" />
                    Save image note
                  </>
                )}
              </button>
            </div>
            </div>
          ) : null}
          </>
        ) : null}

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
