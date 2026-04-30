import { useCallback } from 'react';
import { Mic, MicOff } from 'lucide-react';
import { v4 as uuidv4 } from 'uuid';
import { db } from '../db';
import type { LocalNote } from '../db';
import { useVoiceRecorder } from '../hooks/useVoiceRecorder';
import { syncManager } from '../sync/syncManager';
import { useAuthStore } from '../store/authStore';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Upload a blob to /api/upload and return the resulting URL. */
async function uploadBlob(blob: Blob, token: string): Promise<string> {
  const formData = new FormData();
  formData.append('file', blob, `audio-${Date.now()}.webm`);

  const res = await fetch('/api/upload', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (!res.ok) {
    throw new Error(`Upload failed: ${res.status}`);
  }

  const json = (await res.json()) as { url: string };
  return json.url;
}

/** POST audio blob to /api/voice/upload for STT; returns the NoteOut. */
async function uploadVoice(
  audioBlob: Blob,
  token: string,
): Promise<{ id: string; content: string; processing_status: string }> {
  const formData = new FormData();
  formData.append('audio', audioBlob, `voice-${Date.now()}.webm`);

  const res = await fetch('/api/voice/upload', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (!res.ok) {
    throw new Error(`Voice upload failed: ${res.status}`);
  }

  return res.json() as Promise<{ id: string; content: string; processing_status: string }>;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface VoiceCaptureProps {
  /** Called after the local note is written to IndexedDB (< 2 s, B9 NFR-1) */
  onNoteCreated?: (localId: string) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * VoiceCapture — floating action button (FAB) for voice recording.
 *
 * Behaviour:
 *  1. Tap to start recording (indigo idle → red+pulse).
 *  2. Tap again to stop.
 *  3. IMMEDIATELY write a LocalNote to IndexedDB with syncStatus='pending',
 *     processingStatus='raw' (B9 NFR-1 — feed reflects in < 2 s).
 *  4. Enqueue create op in syncQueue; call syncManager.pushChanges() if online.
 *  5. If online, also POST audio to /api/voice/upload in background and
 *     update the same row with serverId + transcribed content.
 */
export function VoiceCapture({ onNoteCreated }: VoiceCaptureProps): React.ReactElement {
  const { isRecording, start, stop } = useVoiceRecorder();
  const accessToken = useAuthStore((s) => s.accessToken);

  const handleToggle = useCallback(async () => {
    if (!isRecording) {
      await start();
      return;
    }

    // ------------------------------------------------------------------ stop
    const audioBlob = await stop();
    if (!audioBlob) return; // nothing was recorded

    const localId = uuidv4();
    const now = new Date();

    // B9 NFR-1: IMMEDIATE IndexedDB write — feed updates synchronously
    const localNote: LocalNote = {
      localId,
      content: '',          // will be filled by STT response
      rawTranscription: '',
      sourceType: 'voice',
      category: 'Ideas',   // default; AI will correct after processing
      audioBlob,
      tags: [],
      syncStatus: 'pending',
      processingStatus: 'raw',
      createdAt: now,
      updatedAt: now,
    };

    await db.notes.add(localNote);

    // Enqueue sync operation
    await db.syncQueue.add({
      operation: 'create',
      entityType: 'note',
      entityId: localId,
      payload: { localId },
      timestamp: now,
      retryCount: 0,
    });

    // Notify parent so LibraryPage can react
    onNoteCreated?.(localId);

    // If online, trigger sync engine (which will push the queue FIFO)
    if (navigator.onLine) {
      void syncManager.pushChanges();
    }

    // Background: if online and authenticated, also call /api/voice/upload
    // for immediate STT response (updates the same row when done)
    if (navigator.onLine && accessToken) {
      void (async () => {
        try {
          // Upload audio blob
          try {
            await uploadBlob(audioBlob, accessToken);
          } catch {
            // Non-fatal: syncManager will handle this via the queue
          }

          // POST to /api/voice/upload for STT + note creation
          const noteOut = await uploadVoice(audioBlob, accessToken);

          // Update the local row with the server response
          await db.notes.update(localId, {
            serverId: noteOut.id,
            content: noteOut.content,
            rawTranscription: noteOut.content,
            audioBlob: undefined,       // no need to keep the blob after successful upload
            syncStatus: 'synced',
            processingStatus: noteOut.processing_status as LocalNote['processingStatus'],
            updatedAt: new Date(),
          });

          // Remove from sync queue since we handled it inline
          const queueItem = await db.syncQueue
            .where('entityId')
            .equals(localId)
            .first();
          if (queueItem?.id !== undefined) {
            await db.syncQueue.delete(queueItem.id);
          }
        } catch {
          // Leave syncStatus='pending' — syncManager will retry via queue
        }
      })();
    }
  }, [isRecording, start, stop, accessToken, onNoteCreated]);

  return (
    <button
      type="button"
      aria-label={isRecording ? 'Stop recording' : 'Start recording'}
      onClick={() => void handleToggle()}
      className={[
        'fixed bottom-24 right-6 z-50',
        'flex h-16 w-16 items-center justify-center rounded-full shadow-lg',
        'transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2',
        isRecording
          ? 'bg-red-500 animate-pulse scale-110 focus:ring-red-400'
          : 'bg-indigo-600 hover:bg-indigo-500 focus:ring-indigo-400',
      ].join(' ')}
    >
      {isRecording ? (
        <MicOff className="h-7 w-7 text-white" aria-hidden="true" />
      ) : (
        <Mic className="h-7 w-7 text-white" aria-hidden="true" />
      )}
    </button>
  );
}

export default VoiceCapture;
