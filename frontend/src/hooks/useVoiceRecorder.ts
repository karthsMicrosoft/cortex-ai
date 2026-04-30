import { useCallback, useRef, useState } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UseVoiceRecorderReturn {
  isRecording: boolean;
  /** Partial live transcript text (updated while recording via STT events) */
  partialText: string;
  /** Start recording — resolves when MediaRecorder is running */
  start: () => Promise<void>;
  /** Stop recording — resolves with the accumulated audio Blob, or undefined if not recording */
  stop: () => Promise<Blob | undefined>;
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
 * Returns { isRecording, partialText, start, stop }.
 */
export function useVoiceRecorder(): UseVoiceRecorderReturn {
  const [isRecording, setIsRecording] = useState(false);
  const [partialText, setPartialText] = useState('');

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const resolveStopRef = useRef<((blob: Blob) => void) | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const start = useCallback(async (): Promise<void> => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      return; // already recording
    }

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;

    const mimeType = 'audio/webm';
    const recorder = new MediaRecorder(stream, { mimeType });
    mediaRecorderRef.current = recorder;
    chunksRef.current = [];
    setPartialText('');

    recorder.ondataavailable = (event: BlobEvent) => {
      if (event.data && event.data.size > 0) {
        chunksRef.current.push(event.data);
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
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        chunksRef.current = [];

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

  /**
   * Exposed for callers that receive partial STT text from a WebSocket and want
   * to surface it in the UI while recording is still in progress.
   */
  (useVoiceRecorder as unknown as { _setPartialText?: (t: string) => void })._setPartialText =
    setPartialText;

  return { isRecording, partialText, start, stop };
}

// Utility: allow external callers (e.g. a WS handler) to push partial transcript
// text into the hook's state without coupling the hook to transport details.
export function setPartialTranscript(
  recorder: UseVoiceRecorderReturn & { _setPartialText?: (t: string) => void },
  text: string,
): void {
  if (recorder._setPartialText) {
    recorder._setPartialText(text);
  }
}
