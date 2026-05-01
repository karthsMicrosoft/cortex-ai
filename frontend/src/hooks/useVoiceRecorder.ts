import { useCallback, useRef, useState } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UseVoiceRecorderReturn {
  isRecording: boolean;
  /** Partial live transcript text (updated while recording via STT events) */
  partialText: string;
  /** Ref to an externally-provided WebSocket for streaming mode. */
  wsRef: React.MutableRefObject<WebSocket | null>;
  /**
   * Attach a WebSocket to this recorder instance.
   * Once attached, every `ondataavailable` chunk is forwarded as an ArrayBuffer
   * to `ws.send()` when the WS is OPEN (alongside local chunk accumulation).
   */
  setWs: (ws: WebSocket | null) => void;
  /** Start recording — resolves when MediaRecorder is running */
  start: () => Promise<void>;
  /** Stop recording — resolves with the accumulated audio Blob, or undefined if not recording */
  stop: () => Promise<Blob | undefined>;
  /**
   * Internal — exposed so setPartialTranscript() can imperatively update partialText.
   * @internal
   */
  _setPartialText?: (text: string) => void;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * useVoiceRecorder
 *
 * Wraps the browser MediaRecorder API (mimeType: 'audio/webm').
 * Accumulates ondataavailable chunks and resolves the Blob on stop.
 *
 * Exposes:
 *  - `wsRef` / `setWs`: callers can attach a WebSocket; chunks are forwarded
 *    as ArrayBuffers every 250ms alongside local accumulation (offline fallback).
 *  - `_setPartialText`: internal hook for setPartialTranscript() helper.
 *
 * Returns { isRecording, partialText, wsRef, setWs, start, stop }.
 */
export function useVoiceRecorder(): UseVoiceRecorderReturn {
  const [isRecording, setIsRecording] = useState(false);
  const [partialText, setPartialText] = useState('');

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const resolveStopRef = useRef<((blob: Blob) => void) | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  // WebSocket ref — can be set externally via setWs()
  const wsRef = useRef<WebSocket | null>(null);

  const setWs = useCallback((ws: WebSocket | null) => {
    wsRef.current = ws;
  }, []);

  const start = useCallback(async (): Promise<void> => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      return; // already recording
    }

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;

    // Pick the first MIME type the browser supports. iOS Safari supports audio/mp4
    // but not audio/webm. Chrome/Firefox prefer audio/webm. The backend ffmpeg
    // conversion path in speech.py handles any container ffmpeg understands.
    const PREFERRED_TYPES = ['audio/webm', 'audio/mp4', 'audio/ogg'];
    const mimeType = PREFERRED_TYPES.find((t) => MediaRecorder.isTypeSupported(t)) ?? '';
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    mediaRecorderRef.current = recorder;
    chunksRef.current = [];
    setPartialText('');

    recorder.ondataavailable = (event: BlobEvent) => {
      if (event.data && event.data.size > 0) {
        // Always accumulate locally (offline-first fallback)
        chunksRef.current.push(event.data);

        // Forward to WS as ArrayBuffer when WS is open
        const ws = wsRef.current;
        if (ws && ws.readyState === WebSocket.OPEN) {
          // Try arrayBuffer() first (preferred for binary WS frames);
          // fall back to sending the Blob directly if arrayBuffer is unavailable.
          const sendChunk = (buf: ArrayBuffer | Blob) => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(buf);
            }
          };
          if (typeof event.data.arrayBuffer === 'function') {
            void event.data.arrayBuffer().then(sendChunk);
          } else {
            sendChunk(event.data);
          }
        }
      }
    };

    recorder.start(250); // collect chunks every 250 ms
    setIsRecording(true);
  }, []);

  const stop = useCallback((): Promise<Blob | undefined> => {
    return new Promise<Blob | undefined>((resolve) => {
      const recorder = mediaRecorderRef.current;

      if (!recorder || recorder.state === 'inactive') {
        // Nothing was recording — return undefined (test expectation)
        resolve(undefined);
        return;
      }

      resolveStopRef.current = resolve;

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        chunksRef.current = [];

        // Clear WS ref on stop
        wsRef.current = null;

        // Stop all tracks so the mic indicator clears
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((t) => t.stop());
          streamRef.current = null;
        }

        setIsRecording(false);

        if (resolveStopRef.current) {
          resolveStopRef.current(blob);
          resolveStopRef.current = null;
        }
      };

      recorder.stop();
    });
  }, []);

  return {
    isRecording,
    partialText,
    wsRef,
    setWs,
    start,
    stop,
    _setPartialText: setPartialText,
  };
}

// ---------------------------------------------------------------------------
// Utility: allow external callers (e.g. a WS onmessage handler) to push
// partial transcript text into the hook's state reactively.
// ---------------------------------------------------------------------------

export function setPartialTranscript(
  recorder: Pick<UseVoiceRecorderReturn, '_setPartialText'>,
  text: string,
): void {
  if (recorder._setPartialText) {
    recorder._setPartialText(text);
  }
}
