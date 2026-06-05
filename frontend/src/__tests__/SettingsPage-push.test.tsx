import '@testing-library/jest-dom';
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PushStatus } from '../services/push';

const pushMocks = vi.hoisted(() => ({
  getPushStatus: vi.fn(),
  requestPermission: vi.fn(),
  subscribeToPush: vi.fn(),
  unsubscribeFromPush: vi.fn(),
}));

vi.mock('../services/push', () => ({
  getPushStatus: pushMocks.getPushStatus,
  requestPermission: pushMocks.requestPermission,
  subscribeToPush: pushMocks.subscribeToPush,
  unsubscribeFromPush: pushMocks.unsubscribeFromPush,
}));

vi.mock('../api/auth', () => ({
  changePassword: vi.fn(),
  mintClipToken: vi.fn(),
}));

vi.mock('../api/export', () => ({
  downloadExport: vi.fn(),
}));

vi.mock('../components/PersonalDictionary', () => ({
  PersonalDictionary: () => <div data-testid="personal-dictionary-mock" />,
}));

vi.mock('../components/ShadowReaderSettings', () => ({
  ShadowReaderSettings: () => <div data-testid="shadow-reader-settings-mock" />,
}));

vi.mock('../store/authStore', () => {
  const state = {
    accessToken: 'test-token',
    user: { id: 'u1' },
    signOut: vi.fn(),
  };
  const store = Object.assign(
    (selector: (s: typeof state) => unknown) => selector(state),
    { getState: () => state, subscribe: () => () => {}, setState: () => {} },
  );
  return { useAuthStore: store };
});

async function renderSettingsPage(status: PushStatus) {
  pushMocks.getPushStatus.mockResolvedValue(status);
  const mod = await import('../pages/SettingsPage');
  const SettingsPage = mod.default;
  render(
    <MemoryRouter initialEntries={['/settings']}>
      <Routes>
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return screen.findByRole('switch', { name: /enable reminder notifications/i });
}

beforeEach(() => {
  vi.clearAllMocks();
  pushMocks.requestPermission.mockResolvedValue('granted');
  pushMocks.subscribeToPush.mockResolvedValue({ endpoint: 'https://push.example/1' });
  pushMocks.unsubscribeFromPush.mockResolvedValue(true);
});

describe('SettingsPage reminder notification toggle', () => {
  it.each([
    ['unsupported', false, true],
    ['unavailable', false, true],
    ['denied', false, false],
    ['unsubscribed', false, false],
    ['subscribed', true, false],
  ] as Array<[PushStatus, boolean, boolean]>)('reflects %s status', async (status, checked, disabled) => {
    const toggle = await renderSettingsPage(status);
    await waitFor(() => {
      expect(toggle).toHaveProperty('checked', checked);
      if (disabled) expect(toggle).toBeDisabled();
      else expect(toggle).not.toBeDisabled();
    });
  });

  it('toggling on requests permission and subscribes to push', async () => {
    const toggle = await renderSettingsPage('unsubscribed');

    await act(async () => {
      fireEvent.click(toggle);
    });

    await waitFor(() => {
      expect(pushMocks.requestPermission).toHaveBeenCalledTimes(1);
      expect(pushMocks.subscribeToPush).toHaveBeenCalledTimes(1);
      expect(toggle).toHaveProperty('checked', true);
    });
  });

  it('toggling off unsubscribes from push', async () => {
    const toggle = await renderSettingsPage('subscribed');

    await act(async () => {
      fireEvent.click(toggle);
    });

    await waitFor(() => {
      expect(pushMocks.unsubscribeFromPush).toHaveBeenCalledTimes(1);
      expect(toggle).toHaveProperty('checked', false);
    });
  });

  it('shows the iOS install hint for unsupported iPhone browsers', async () => {
    Object.defineProperty(navigator, 'userAgent', {
      configurable: true,
      value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
    });

    await renderSettingsPage('unsupported');

    expect(await screen.findByText(/ios users: add cortex to your home screen first/i)).toBeInTheDocument();
  });

  it('shows the denied explanatory message', async () => {
    await renderSettingsPage('denied');

    expect(
      await screen.findByText(/notifications are blocked — enable in your browser\/system settings/i),
    ).toBeInTheDocument();
  });

  describe('launcher-record toggle (Round 36)', () => {
    beforeEach(() => {
      try {
        window.localStorage.removeItem('cortex_launcher_record');
      } catch {
        // ignore
      }
    });

    it('renders unchecked by default and persists ON to localStorage', async () => {
      await renderSettingsPage('unsubscribed');
      const launcher = await screen.findByRole('switch', { name: /use record screen as launcher/i });

      expect(launcher).toHaveProperty('checked', false);

      await act(async () => {
        fireEvent.click(launcher);
      });

      await waitFor(() => {
        expect(launcher).toHaveProperty('checked', true);
      });
      expect(window.localStorage.getItem('cortex_launcher_record')).toBe('1');
    });

    it('initializes from localStorage when flag is set', async () => {
      window.localStorage.setItem('cortex_launcher_record', '1');
      await renderSettingsPage('unsubscribed');
      const launcher = await screen.findByRole('switch', { name: /use record screen as launcher/i });
      expect(launcher).toHaveProperty('checked', true);
    });

    it('toggling off removes the localStorage entry', async () => {
      window.localStorage.setItem('cortex_launcher_record', '1');
      await renderSettingsPage('unsubscribed');
      const launcher = await screen.findByRole('switch', { name: /use record screen as launcher/i });

      await act(async () => {
        fireEvent.click(launcher);
      });

      await waitFor(() => {
        expect(launcher).toHaveProperty('checked', false);
      });
      expect(window.localStorage.getItem('cortex_launcher_record')).toBeNull();
    });
  });
});
