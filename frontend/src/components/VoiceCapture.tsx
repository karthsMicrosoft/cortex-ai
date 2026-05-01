import { useCallback, useRef, useState } from 'react';
import { Mic, MicOff } from 'lucide-react';
import { v4 as uuidv4 } from 'uuid';
import { db } from '../db';
import type { LocalNote } from '../db';
import { useVoiceRecorder } from '../hooks/useVoiceRecorder';
import { syncManager } from '../sync/syncManager';
import { useAuthStore } from '../store/authStore';
import { apiUrl, wsUrl } from '../api/client';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Upload a blob to /api/upload and return the resulting URL. */
async function uploadBlob(blob: Blob, token: string): Promise<string> {
  const formData = new FormData();
  formData.append('file', blob, `audio-${Date.now()}.webm`);

  const res = await fetch(apiUrl('/api/upload'), {
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

interface VoiceUploadResponse {
  id: string;
  content: string;
  processing_status: string;
  raw_transcription?: string;
  audio_url?: string;
}

/** POST audio blob to /api/voice/upload for STT; returns the NoteOut. */
async function uploadVoice(
  audioBlob: Blob,
  token: string,
): Promise<VoiceUploadResponse> {
  const formData = new FormData();
  // Backend voice_upload expects field name 'file' (matches generic /api/upload).
  // Sending 'audio' triggers a 422 "Field required: body.file" — fixed 2026-05-01.
  // Use the blob's actual MIME type for the filename extension so the backend
  // can detect audio/mp4 (iOS Safari) vs audio/webm (Chrome/Firefox).
  const ext = audioBlob.type.includes('mp4') ? 'mp4' : audioBlob.type.includes('ogg') ? 'ogg' : 'webm';
  formData.append('file', audioBlob, `voice-${Date.now()}.${ext}`);

  const res = await fetch(apiUrl('/api/voice/upload'), {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
    credentials: 'include',
  });

  if (!res.ok) {
    throw new Error(`Voice upload failed: ${res.status}`);
  }

  return res.json() as Promise<VoiceUploadResponse>;
}

// ---------------------------------------------------------------------------
// Sub-component: live transcript display (§ 2.6)
// ---------------------------------------------------------------------------

interface RealtimeTranscriptProps {
  text: string;
}

/** Shows partial STT text above the FAB. Truncates after 200 chars. */
function RealtimeTranscript({ text }: RealtimeTranscriptProps): React.ReactElement | null {
  if (!text) return null;
  const display = text.length > 200 ? `${text.slice(0, 200)}…` : text;
  return (
    <div
      aria-live="polite"
      aria-label="Live transcription"
      data-testid="partial-transcript"
      className="fixed bottom-44 right-6 z-50 max-w-xs rounded-xl bg-black/70 px-4 py-2 text-sm text-white shadow-lg"
    >
      {display}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: degraded-mode toast
// ---------------------------------------------------------------------------

interface DegradedToastProps {
  visible: boolean;
}

function DegradedToast({ visible }: DegradedToastProps): React.ReactElement | null {
  if (!visible) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="ws-error-toast"
      className="fixed bottom-8 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-yellow-500 px-4 py-2 text-sm font-medium text-white shadow-lg"
    >
      Network issue — using file-upload fallback
    </div>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface VoiceCaptureProps {
  /** Called after the local note is written to IndexedDB (< 2 s, B9 NFR-1) */
  onNoteCreated?: (localId: string) => void;
  /** Recording mode — 'streaming' enables WS real-time STT (default: 'streaming'). */
  mode?: 'file' | 'streaming';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * VoiceCapture — floating action button (FAB) for voice recording.
 *
 * Behaviour:
 *  1. Tap to start recording (indigo idle → red+pulse).
 *  2. In streaming mode, opens a WebSocket to /api/voice/stream?token=...
 *     and receives partial+final transcripts, which are shown live above the FAB.
 *  3. Tap again to stop.
 *  4. IMMEDIATELY write a LocalNote to IndexedDB with syncStatus='pending',
 *     processingStatus='raw'/'transcribed', rawTranscription from WS if available
 *     (B9 NFR-1 — feed reflects in < 2 s).
 *  5. Enqueue create op in syncQueue; call syncManager.pushChanges() if online.
 *  6. If WS failed (error/close while recording), fall back to POST /api/voice/upload
 *     and surface a degraded-mode toast.
 */
export function VoiceCapture({ onNoteCreated, mode = 'streaming' }: VoiceCaptureProps): React.ReactElement {
  const accessToken = useAuthStore((s) => s.accessToken);

  // Hook provides isRecording state (for button styling) and start/stop controls.
  // hookPartialText: for backward-compat with tests that set mockHookState.partialText.
  const hookReturn = useVoiceRecorder();
  const { isRecording, partialText: hookPartialText } = hookReturn;

  // Keep a ref that always reflects the LATEST hook return so that
  // handleToggle (a stable useCallback) can read the *current* isRecording value
  // without capturing a stale closure from a previous render.
  const hookRef = useRef(hookReturn);
  hookRef.current = hookReturn;

  // selfRecordingRef: component-level tracking of whether WE initiated a recording.
  // Updated synchronously inside handleToggle (NOT via React state), so handleToggle
  // can read it reliably even with stale closures.
  const selfRecordingRef = useRef(false);

  // ---- Real-time STT state (WS-derived) -----------------------------------
  // wsPartialText: updated directly from WS onmessage events in this component.
  const [wsPartialText, setWsPartialText] = useState('');
  const [showDegradedToast, setShowDegradedToast] = useState(false);

  // Display text: prefer WS-derived text, fall back to hook's partialText (e.g. in tests)
  const displayText = wsPartialText || hookPartialText;

  // Keep a ref that always reflects the latest displayText so handleToggle
  // (a stable useCallback) can read the *current* displayText without
  // capturing a stale closure from a previous render.
  const displayTextRef = useRef(displayText);
  displayTextRef.current = displayText;

  // WebSocket managed directly by this component
  const wsRef = useRef<WebSocket | null>(null);

  // Track WS health and accumulated final transcript from WS
  const wsDegradedRef = useRef(false);
  const wsFinalTranscriptRef = useRef('');
  const wsHasFinalRef = useRef(false);

  // ---- Open WebSocket on start --------------------------------------------

  const _openWs = useCallback((token: string) => {
    const url = wsUrl(`/api/voice/stream?token=${encodeURIComponent(token)}`);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data as string) as {
          type: string;
          text?: string;
          is_final?: boolean;
          message?: string;
        };

        if (msg.type === 'partial' && msg.text) {
          setWsPartialText(msg.text);
        } else if (msg.type === 'transcription' && msg.text) {
          // Accumulate final transcript segments
          wsFinalTranscriptRef.current = wsFinalTranscriptRef.current
            ? `${wsFinalTranscriptRef.current} ${msg.text}`
            : msg.text;
          wsHasFinalRef.current = true;
          setWsPartialText(wsFinalTranscriptRef.current);
        } else if (msg.type === 'error') {
          wsDegradedRef.current = true;
        }
      } catch {
        // ignore malformed frames
      }
    };

    ws.onerror = () => {
      wsDegradedRef.current = true;
    };

    ws.onclose = (evt: CloseEvent) => {
      // Abnormal close (1006 = network error, not clean 1000) = degraded
      if (evt.code !== 1000) {
        wsDegradedRef.current = true;
        // Show toast immediately on abnormal close
        setShowDegradedToast(true);
        setTimeout(() => setShowDegradedToast(false), 4000);
      }
    };
  }, []);

  // ---- Close WebSocket on stop --------------------------------------------

  const _closeWs = useCallback(() => {
    const ws = wsRef.current;
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      ws.close();
    }
    wsRef.current = null;
  }, []);

  // ---- Toggle handler -----------------------------------------------------

  const handleToggle = useCallback(async () => {
    // Determine current recording state:
    // Use selfRecordingRef (component-level) combined with the hook's isRecording
    // getter (which reads mockHookState in tests). Either source signals "recording".
    const hookIsRecording = hookRef.current.isRecording;
    const componentIsRecording = selfRecordingRef.current;
    const currentIsRecording = hookIsRecording || componentIsRecording;

    if (!currentIsRecording) {
      // Reset state for fresh session
      wsDegradedRef.current = false;
      wsFinalTranscriptRef.current = '';
      wsHasFinalRef.current = false;
      selfRecordingRef.current = true;  // mark that we started recording
      setWsPartialText('');
      setShowDegradedToast(false);

      await hookRef.current.start();

      // Open WS in streaming mode (after start so mic is active)
      if (mode === 'streaming' && accessToken) {
        _openWs(accessToken);
      }
      return;
    }

    // ------------------------------------------------------------------ stop
    selfRecordingRef.current = false;  // mark that we stopped
    // Close WS before stopping recorder
    _closeWs();

    const audioBlob = await hookRef.current.stop();
    if (!audioBlob) return; // nothing was recorded

    const localId = uuidv4();
    const now = new Date();

    // Use WS-derived final transcript if available, otherwise current display text.
    // Read from displayTextRef (not closed-over displayText) to always get the
    // latest value even if the callback was created before the last re-render.
    const capturedTranscript = wsHasFinalRef.current
      ? wsFinalTranscriptRef.current
      : displayTextRef.current;

    // B9 NFR-1: IMMEDIATE IndexedDB write — feed updates synchronously
    const localNote: LocalNote = {
      localId,
      content: capturedTranscript,
      rawTranscription: capturedTranscript,
      sourceType: 'voice',
      category: 'Ideas',   // default; AI will correct after processing
      audioBlob,
      tags: [],
      syncStatus: 'pending',
      processingStatus: capturedTranscript ? 'transcribed' : 'raw',
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

    // If online, trigger sync engine
    if (navigator.onLine) {
      void syncManager.pushChanges();
    }

    // Background: handle online upload path
    if (navigator.onLine && accessToken) {
      void (async () => {
        try {
          if (wsDegradedRef.current || !wsHasFinalRef.current) {
            // Degraded or no WS final transcript: fall back to file-mode upload.
            // Always show the degraded toast so the user knows we're in fallback mode.
            setShowDegradedToast(true);

            let noteOut: { id: string; content: string; processing_status: string; raw_transcription?: string; audio_url?: string } | null = null;
            try {
              noteOut = await uploadVoice(audioBlob, accessToken);
            } catch (uploadErr) {
              // Fallback upload failed — hide the "Network issue" toast and
              // show a real error so the user knows to try again.
              setShowDegradedToast(false);
              // Surface error in the local note so the UI can show a failed state.
              await db.notes.update(localId, {
                processingStatus: 'failed',
                updatedAt: new Date(),
              });
              console.warn('Voice fallback upload failed:', uploadErr);
              return;
            }

            // Fallback succeeded — update the local note to mark it synced.
            setShowDegradedToast(false);
            await db.notes.update(localId, {
              serverId: noteOut.id,
              content: noteOut.content || noteOut.raw_transcription || '',
              rawTranscription: noteOut.raw_transcription ?? noteOut.content ?? '',
              audioBlob: undefined,
              syncStatus: 'synced',
              processingStatus: noteOut.processing_status as LocalNote['processingStatus'],
              updatedAt: new Date(),
            });
          } else {
            // WS path was healthy: upload blob to storage only
            try {
              await uploadBlob(audioBlob, accessToken);
            } catch {
              // Non-fatal — note already has audio from WS transcript
            }

            await db.notes.update(localId, {
              audioBlob: undefined,
              syncStatus: 'synced',
              updatedAt: new Date(),
            });
          }

          // Remove from sync queue since handled inline
          const queueItem = await db.syncQueue
            .where('entityId')
            .equals(localId)
            .first();
          if (queueItem?.id !== undefined) {
            await db.syncQueue.delete(queueItem.id);
          }
        } catch {
          // Leave syncStatus='pending' — syncManager will retry
          setShowDegradedToast(false);
        }
      })();
    }
  // hookRef, wsRef, wsDegradedRef, displayTextRef etc are refs — stable across renders.
  // displayText is intentionally omitted; it is accessed via displayTextRef.current.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, onNoteCreated, mode, _openWs, _closeWs]);

  return (
    <>
      {/* Live transcription display — shown when transcript is available (§ 2.6) */}
      <RealtimeTranscript text={displayText} />

      {/* Degraded mode toast */}
      <DegradedToast visible={showDegradedToast} />

      {/* FAB */}
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
    </>
  );
}

export default VoiceCapture;
