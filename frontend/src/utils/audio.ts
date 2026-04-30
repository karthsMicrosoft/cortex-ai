/**
 * Audio utilities for voice capture — used by VoiceCapture (US-4).
 */

/**
 * Request microphone access and return the MediaStream.
 * Throws if permission is denied or microphone is unavailable.
 */
export async function getMicStream(): Promise<MediaStream> {
  return navigator.mediaDevices.getUserMedia({ audio: true, video: false });
}

/**
 * Create a MediaRecorder from a MediaStream.
 * Prefers audio/webm (most browsers) with a 250ms timeslice.
 */
export function createMediaRecorder(
  stream: MediaStream,
  onDataAvailable: (chunk: Blob) => void,
): MediaRecorder {
  const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
    ? 'audio/webm;codecs=opus'
    : MediaRecorder.isTypeSupported('audio/webm')
    ? 'audio/webm'
    : '';

  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

  recorder.ondataavailable = (e: BlobEvent) => {
    if (e.data && e.data.size > 0) {
      onDataAvailable(e.data);
    }
  };

  return recorder;
}

/**
 * Merge recorded Blob chunks into a single audio/webm Blob.
 */
export function blobsToWebm(chunks: Blob[]): Blob {
  return new Blob(chunks, { type: 'audio/webm' });
}
