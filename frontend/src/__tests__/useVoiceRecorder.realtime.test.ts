/**
 * US-9 — useVoiceRecorder hook + WebSocket integration tests (TDD red)
 *
 * Covers (per task file task 2.1):
 *
 *  2.1  The hook exposes a wsRef so callers can wire a WS.
 *       Every 250ms audio chunk (ondataavailable) is forwarded to the WS
 *       as an ArrayBuffer alongside the existing chunk accumulation.
 *       Chunks continue to accumulate locally for the offline-first fallback.
 *
 * Additional integration tests:
 *  - WS message listener updates partialText state
 *  - setPartialTranscript helper updates partialText on hook instance
 *  - wsRef.current is null before WS is attached, set once attached
 *  - Sending on a closed WS does not throw
 *
 * Mock strategy:
 *  - MockMediaRecorder (same pattern as useVoiceRecorder.test.ts)
 *  - Fake WebSocket with controllable ondataavailable → send pipeline
 *  - renderHook from @testing-library/react
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// ---------------------------------------------------------------------------
// MediaRecorder mock (reuse same structure as existing test)
// ---------------------------------------------------------------------------

type EventHandler = (event: Event) => void;

class MockMediaRecorder {
  static isTypeSupported = vi.fn().mockReturnValue(true);

  state: 'inactive' | 'recording' | 'paused' = 'inactive';
  mimeType: string;
  ondataavailable: ((evt: BlobEvent) => void) | null = null;
  onstop: EventHandler | null = null;
  onerror: EventHandler | null = null;

  // Expose so tests can fire chunks
  static lastInstance: MockMediaRecorder | null = null;

  constructor(_stream: MediaStream, options?: { mimeType?: string }) {
    this.mimeType = options?.mimeType ?? 'audio/webm';
    MockMediaRecorder.lastInstance = this;
  }

  start(_timeslice?: number) {
    this.state = 'recording';
  }

  stop() {
    this.state = 'inactive';
    const blob = new Blob(['audio-chunk'], { type: this.mimeType });
    if (this.ondataavailable) {
      const event = new Event('dataavailable') as unknown as BlobEvent;
      Object.defineProperty(event, 'data', { value: blob });
      this.ondataavailable(event);
    }
    if (this.onstop) {
      this.onstop(new Event('stop'));
    }
  }

  /** Test helper — fire a manual dataavailable event with a custom blob. */
  fireDataAvailable(blob: Blob) {
    if (this.ondataavailable) {
      const event = new Event('dataavailable') as unknown as BlobEvent;
      Object.defineProperty(event, 'data', { value: blob });
      this.ondataavailable(event);
    }
  }
}

// ---------------------------------------------------------------------------
// WebSocket mock
// ---------------------------------------------------------------------------

interface MockWsInstance {
  url: string;
  readyState: number;
  onopen: ((e: Event) => void) | null;
  onmessage: ((e: MessageEvent) => void) | null;
  onerror: ((e: Event) => void) | null;
  onclose: ((e: CloseEvent) => void) | null;
  send: ReturnType<typeof vi.fn>;
  close: ReturnType<typeof vi.fn>;
  _emit: (type: string, data: object) => void;
}

let lastWsMock: MockWsInstance | null = null;

class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;

  url: string;
  readyState = MockWebSocket.OPEN;
  onopen: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;
  send = vi.fn();
  close = vi.fn().mockImplementation(() => {
    this.readyState = MockWebSocket.CLOSED;
  });

  constructor(url: string) {
    this.url = url;
    lastWsMock = this as unknown as MockWsInstance;
    Promise.resolve().then(() => {
      if (this.onopen) this.onopen(new Event('open'));
    });
  }

  _emit(type: string, data: object) {
    if (this.onmessage) {
      this.onmessage(
        new MessageEvent('message', { data: JSON.stringify({ type, ...data }) }),
      );
    }
  }
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

let mockStream: MediaStream;

beforeEach(() => {
  MockMediaRecorder.lastInstance = null;
  lastWsMock = null;

  mockStream = {
    getTracks: () => [{ stop: vi.fn() }],
  } as unknown as MediaStream;

  Object.defineProperty(navigator, 'mediaDevices', {
    value: {
      getUserMedia: vi.fn().mockResolvedValue(mockStream),
    },
    writable: true,
    configurable: true,
  });

  (global as unknown as Record<string, unknown>).MediaRecorder = MockMediaRecorder;
  vi.stubGlobal('WebSocket', MockWebSocket);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// Import hook under test
// ---------------------------------------------------------------------------

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let useVoiceRecorder: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let setPartialTranscript: any;

beforeEach(async () => {
  const mod = await import('../hooks/useVoiceRecorder');
  useVoiceRecorder = mod.useVoiceRecorder;
  setPartialTranscript = mod.setPartialTranscript;
});

// ---------------------------------------------------------------------------
// Task 2.1 — wsRef exposure
// ---------------------------------------------------------------------------

describe('useVoiceRecorder — Task 2.1 wsRef exposure', () => {
  it('hook return value includes a wsRef property', () => {
    const { result } = renderHook(() => useVoiceRecorder());
    expect(result.current).toHaveProperty('wsRef');
  });

  it('wsRef.current is null before a WS is attached', () => {
    const { result } = renderHook(() => useVoiceRecorder());
    expect(result.current.wsRef?.current).toBeNull();
  });

  it('hook provides a way to attach a WebSocket (setWs or wsRef)', () => {
    const { result } = renderHook(() => useVoiceRecorder());
    // Either setWs function or direct wsRef should be available
    const hasSetWs = typeof result.current.setWs === 'function';
    const hasWsRef = 'wsRef' in result.current;
    expect(hasSetWs || hasWsRef).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Task 2.1 — ondataavailable chunks forwarded to WS
// ---------------------------------------------------------------------------

describe('useVoiceRecorder — Task 2.1 chunk forwarding', () => {
  it('audio chunk from MediaRecorder is forwarded to ws.send() when WS is open', async () => {
    const { result } = renderHook(() => useVoiceRecorder());

    await act(async () => {
      await result.current.start();
    });

    // Attach a WS to the hook
    const fakeWs = new MockWebSocket('ws://localhost/api/voice/stream?token=t');
    fakeWs.readyState = MockWebSocket.OPEN;

    if (typeof result.current.setWs === 'function') {
      act(() => {
        result.current.setWs(fakeWs);
      });
    } else if (result.current.wsRef) {
      result.current.wsRef.current = fakeWs;
    }

    // Fire a dataavailable event from the recorder
    await act(async () => {
      const recorder = MockMediaRecorder.lastInstance;
      if (recorder) {
        const chunk = new Blob(['pcm-data'], { type: 'audio/webm' });
        recorder.fireDataAvailable(chunk);
      }
    });

    // ws.send should have been called with the chunk (as ArrayBuffer or Blob)
    await waitForCondition(() => fakeWs.send.mock.calls.length > 0, 500);
    expect(fakeWs.send).toHaveBeenCalled();
  });

  it('chunk is not lost from local accumulation when WS is open', async () => {
    const { result } = renderHook(() => useVoiceRecorder());

    await act(async () => {
      await result.current.start();
    });

    const fakeWs = new MockWebSocket('ws://localhost/api/voice/stream?token=t');
    if (typeof result.current.setWs === 'function') {
      act(() => result.current.setWs(fakeWs));
    } else if (result.current.wsRef) {
      result.current.wsRef.current = fakeWs;
    }

    // Fire a chunk
    await act(async () => {
      const recorder = MockMediaRecorder.lastInstance;
      if (recorder) {
        recorder.fireDataAvailable(new Blob(['pcm'], { type: 'audio/webm' }));
      }
    });

    // stop() should still resolve with a Blob (local accumulation intact)
    let blob: Blob | undefined;
    await act(async () => {
      blob = await result.current.stop();
    });

    expect(blob).toBeInstanceOf(Blob);
    expect(blob!.size).toBeGreaterThan(0);
  });

  it('does not throw if WS is null when chunk arrives', async () => {
    const { result } = renderHook(() => useVoiceRecorder());

    await act(async () => {
      await result.current.start();
    });

    // No WS attached — ondataavailable must not crash
    await expect(
      act(async () => {
        const recorder = MockMediaRecorder.lastInstance;
        if (recorder) {
          recorder.fireDataAvailable(new Blob(['pcm'], { type: 'audio/webm' }));
        }
      }),
    ).resolves.not.toThrow();
  });

  it('does not call ws.send when WS readyState is CLOSED', async () => {
    const { result } = renderHook(() => useVoiceRecorder());

    await act(async () => {
      await result.current.start();
    });

    const fakeWs = new MockWebSocket('ws://localhost/api/voice/stream?token=t');
    fakeWs.readyState = MockWebSocket.CLOSED;

    if (typeof result.current.setWs === 'function') {
      act(() => result.current.setWs(fakeWs));
    } else if (result.current.wsRef) {
      result.current.wsRef.current = fakeWs;
    }

    await act(async () => {
      const recorder = MockMediaRecorder.lastInstance;
      if (recorder) {
        recorder.fireDataAvailable(new Blob(['pcm'], { type: 'audio/webm' }));
      }
    });

    expect(fakeWs.send).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// setPartialTranscript helper
// ---------------------------------------------------------------------------

describe('setPartialTranscript helper', () => {
  it('setPartialTranscript is exported as a function', () => {
    expect(typeof setPartialTranscript).toBe('function');
  });

  it('calling setPartialTranscript updates partialText in the hook', async () => {
    const { result } = renderHook(() => useVoiceRecorder());

    expect(result.current.partialText).toBe('');

    act(() => {
      setPartialTranscript(result.current, 'test partial text');
    });

    await act(async () => {});
    expect(result.current.partialText).toBe('test partial text');
  });

  it('does not throw when called on recorder without _setPartialText', () => {
    const fakeRecorder = { isRecording: false, partialText: '', start: vi.fn(), stop: vi.fn() };
    expect(() => setPartialTranscript(fakeRecorder, 'text')).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// WS message → partialText update
// ---------------------------------------------------------------------------

describe('useVoiceRecorder — WS message → partialText', () => {
  it('partial WS message updates partialText', async () => {
    const { result } = renderHook(() => useVoiceRecorder());

    await act(async () => {
      await result.current.start();
    });

    // Simulate the WS message handler calling setPartialTranscript
    act(() => {
      setPartialTranscript(result.current, 'Partial from WS');
    });

    await act(async () => {});
    expect(result.current.partialText).toBe('Partial from WS');
  });

  it('partialText resets to empty on next start()', async () => {
    const { result } = renderHook(() => useVoiceRecorder());

    await act(async () => {
      await result.current.start();
    });

    act(() => {
      setPartialTranscript(result.current, 'Some text');
    });

    await act(async () => {});
    expect(result.current.partialText).toBe('Some text');

    // Stop and start again — partialText should reset
    await act(async () => {
      await result.current.stop();
    });

    await act(async () => {
      await result.current.start();
    });

    expect(result.current.partialText).toBe('');
  });
});

// ---------------------------------------------------------------------------
// Utility: wait for condition without sleep
// ---------------------------------------------------------------------------

async function waitForCondition(
  condition: () => boolean,
  timeoutMs: number,
): Promise<void> {
  const start = Date.now();
  while (!condition()) {
    if (Date.now() - start > timeoutMs) {
      return; // Time out gracefully — assertion will fail after
    }
    await new Promise((r) => setTimeout(r, 10));
  }
}
