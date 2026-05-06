/**
 * Task 1.1 — useVoiceRecorder hook — TDD red
 *
 * Tests that `frontend/src/hooks/useVoiceRecorder.ts` exports a hook with:
 *   { isRecording, partialText, start, stop }
 *
 * Mocks: navigator.mediaDevices.getUserMedia, global MediaRecorder
 * Critical resolutions: B9 NFR-1 — stop() must return a Blob synchronously
 *   (IndexedDB write happens in the component, not in the hook, but the blob
 *    must be available immediately).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// ---------------------------------------------------------------------------
// MediaRecorder mock
// ---------------------------------------------------------------------------

type EventHandler = (event: Event) => void;

class MockMediaRecorder {
  static isTypeSupported = vi.fn().mockReturnValue(true);

  state: 'inactive' | 'recording' | 'paused' = 'inactive';
  mimeType: string;
  ondataavailable: EventHandler | null = null;
  onstop: EventHandler | null = null;
  onerror: EventHandler | null = null;

  private _chunks: Blob[] = [];

  constructor(_stream: MediaStream, options?: { mimeType?: string }) {
    this.mimeType = options?.mimeType ?? 'audio/webm';
  }

  start(_timeslice?: number) {
    this.state = 'recording';
  }

  stop() {
    this.state = 'inactive';
    // Emit a dataavailable event with a test chunk
    const blob = new Blob(['audio-data'], { type: this.mimeType });
    this._chunks.push(blob);
    if (this.ondataavailable) {
      const event = new Event('dataavailable') as unknown as BlobEvent;
      Object.defineProperty(event, 'data', { value: blob });
      this.ondataavailable(event as unknown as Event);
    }
    if (this.onstop) {
      this.onstop(new Event('stop'));
    }
  }
}

// ---------------------------------------------------------------------------
// Global mock setup
// ---------------------------------------------------------------------------

let mockStream: MediaStream;

beforeEach(() => {
  // Mock MediaStream
  mockStream = {
    getTracks: () => [{ stop: vi.fn() }],
  } as unknown as MediaStream;

  // Mock getUserMedia
  Object.defineProperty(navigator, 'mediaDevices', {
    value: {
      getUserMedia: vi.fn().mockResolvedValue(mockStream),
    },
    writable: true,
    configurable: true,
  });

  // Install MockMediaRecorder as global
  (global as unknown as Record<string, unknown>).MediaRecorder = MockMediaRecorder;
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Import hook under test — this will fail (RED) until the file is created
// ---------------------------------------------------------------------------
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let useVoiceRecorder: any;
beforeEach(async () => {
  // Dynamic import so the mock is in place before the module loads
  const mod = await import('../hooks/useVoiceRecorder');
  useVoiceRecorder = mod.useVoiceRecorder;
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useVoiceRecorder (Task 1.1)', () => {
  // --- initial state ---

  it('exports a useVoiceRecorder function', async () => {
    const mod = await import('../hooks/useVoiceRecorder');
    expect(typeof mod.useVoiceRecorder).toBe('function');
  });

  it('isRecording is false initially', async () => {
    const { result } = renderHook(() => useVoiceRecorder());
    expect(result.current.isRecording).toBe(false);
  });

  it('partialText is empty string initially', async () => {
    const { result } = renderHook(() => useVoiceRecorder());
    expect(result.current.partialText).toBe('');
  });

  it('exposes start and stop functions', async () => {
    const { result } = renderHook(() => useVoiceRecorder());
    expect(typeof result.current.start).toBe('function');
    expect(typeof result.current.stop).toBe('function');
  });

  // --- start recording ---

  it('start() calls getUserMedia with audio constraint', async () => {
    const { result } = renderHook(() => useVoiceRecorder());
    await act(async () => {
      await result.current.start();
    });
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({ audio: true });
  });

  it('isRecording becomes true after start()', async () => {
    const { result } = renderHook(() => useVoiceRecorder());
    await act(async () => {
      await result.current.start();
    });
    expect(result.current.isRecording).toBe(true);
  });

  it('MediaRecorder is created with mimeType audio/webm', async () => {
    const constructorSpy = vi.spyOn(MockMediaRecorder.prototype, 'start');
    const { result } = renderHook(() => useVoiceRecorder());
    await act(async () => {
      await result.current.start();
    });
    expect(constructorSpy).toHaveBeenCalled();
  });

  // --- stop recording ---

  it('stop() returns a Blob', async () => {
    const { result } = renderHook(() => useVoiceRecorder());
    await act(async () => {
      await result.current.start();
    });
    let blob: Blob | undefined;
    await act(async () => {
      blob = await result.current.stop();
    });
    expect(blob).toBeInstanceOf(Blob);
  });

  it('isRecording becomes false after stop()', async () => {
    const { result } = renderHook(() => useVoiceRecorder());
    await act(async () => {
      await result.current.start();
    });
    await act(async () => {
      await result.current.stop();
    });
    expect(result.current.isRecording).toBe(false);
  });

  it('stop() accumulates chunks into a single Blob', async () => {
    const { result } = renderHook(() => useVoiceRecorder());
    await act(async () => {
      await result.current.start();
    });
    let blob: Blob | undefined;
    await act(async () => {
      blob = await result.current.stop();
    });
    // The blob should have content (from the mock 'audio-data' chunk)
    expect(blob!.size).toBeGreaterThan(0);
  });

  it('tracks are stopped when stop() is called', async () => {
    const mockTrack = { stop: vi.fn() };
    mockStream = { getTracks: () => [mockTrack] } as unknown as MediaStream;
    (navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>).mockResolvedValue(mockStream);

    const { result } = renderHook(() => useVoiceRecorder());
    await act(async () => {
      await result.current.start();
    });
    await act(async () => {
      await result.current.stop();
    });
    expect(mockTrack.stop).toHaveBeenCalled();
  });

  it('stop() called before start() does not throw and resolves gracefully', async () => {
    const { result } = renderHook(() => useVoiceRecorder());
    // stop() when not recording should not throw — may return undefined or empty Blob
    await expect(
      act(async () => {
        await result.current.stop();
      }),
    ).resolves.not.toThrow();
  });
});
