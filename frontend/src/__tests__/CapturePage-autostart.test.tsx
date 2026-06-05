import { render, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const { startMock } = vi.hoisted(() => ({
  startMock: vi.fn(),
}));

vi.mock('../components/VoiceCapture', async () => {
  const React = await import('react');
  return {
    VoiceCapture: React.forwardRef(function MockVoiceCapture(
      _props: { onNoteCreated?: (id: string) => void },
      ref: React.ForwardedRef<{ start: () => void }>,
    ) {
      React.useImperativeHandle(ref, () => ({ start: startMock }));
      return React.createElement('div', { 'data-testid': 'voice-capture-fab' }, 'Voice FAB');
    }),
  };
});

vi.mock('../components/SyncIndicator', () => ({
  SyncIndicator: () => <div data-testid="sync-indicator" />,
}));

vi.mock('../components/UrlClipForm', () => ({
  UrlClipForm: () => <div data-testid="url-clip-form" />,
}));

vi.mock('../db', () => ({
  db: {
    notes: { add: vi.fn() },
    syncQueue: { add: vi.fn() },
  },
}));

vi.mock('../sync/syncManager', () => ({
  syncManager: { pushChanges: vi.fn() },
}));

import { CapturePage } from '../pages/CapturePage';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<CapturePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('CapturePage autostart', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts voice capture when autostart=1', async () => {
    renderAt('/?autostart=1');
    await waitFor(() => expect(startMock).toHaveBeenCalledTimes(1));
  });

  it('does not start voice capture without autostart', async () => {
    renderAt('/');
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(startMock).not.toHaveBeenCalled();
  });
});
