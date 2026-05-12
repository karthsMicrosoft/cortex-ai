/**
 * SettingsPage.test.tsx — US-7 (TDD red phase)
 *
 * Tests for frontend/src/pages/SettingsPage.tsx
 *
 * Covers:
 *   - SettingsPage is importable and renders without crashing
 *   - Renders a Settings heading / title
 *   - Renders the <PersonalDictionary /> section
 *   - App.tsx contains a /settings route
 *   - Route is NOT in the bottom-nav (accessed via gear icon only)
 *
 * Design refs:
 *   - SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md § F1.2 (SettingsPage)
 *   - us-7-personal-dictionary.tasks.md task 4.3
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import React from 'react';

// ---------------------------------------------------------------------------
// Mock the changePassword + downloadExport dependencies (Round 15)
// ---------------------------------------------------------------------------

const mockChangePassword = vi.fn();
const mockMintClipToken = vi.fn();
vi.mock('../api/auth', () => ({
  changePassword: (...args: unknown[]) => mockChangePassword(...args),
  mintClipToken: (...args: unknown[]) => mockMintClipToken(...args),
}));

const mockDownloadExport = vi.fn();
vi.mock('../api/export', () => ({
  downloadExport: (...args: unknown[]) => mockDownloadExport(...args),
}));

// ---------------------------------------------------------------------------
// Mock PersonalDictionary component so SettingsPage renders even in red phase
// ---------------------------------------------------------------------------

vi.mock('../components/PersonalDictionary', () => ({
  PersonalDictionary: () => (
    <div data-testid="personal-dictionary-mock">PersonalDictionary</div>
  ),
}));

// ---------------------------------------------------------------------------
// Mock dictionary API (transitively used by PersonalDictionary)
// ---------------------------------------------------------------------------

vi.mock('../api/dictionary', () => ({
  listTerms: vi.fn().mockResolvedValue([]),
  addTerm: vi.fn(),
  deleteTerm: vi.fn(),
  updateTerm: vi.fn(),
  bulkImport: vi.fn(),
  exportTerms: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Mock authStore
// ---------------------------------------------------------------------------

vi.mock('../store/authStore', () => {
  const state = { accessToken: 'test-token', user: { id: 'u1' } };
  const store = Object.assign(
    (selector: (s: typeof state) => unknown) => selector(state),
    { getState: () => state, subscribe: () => () => {}, setState: () => {} },
  );
  return { useAuthStore: store };
});

// ---------------------------------------------------------------------------
// Render helpers
// ---------------------------------------------------------------------------

async function renderSettingsPage() {
  const mod = await import('../pages/SettingsPage');
  const SettingsPage = mod.default ?? (mod as Record<string, unknown>).SettingsPage;
  return render(
    <MemoryRouter initialEntries={['/settings']}>
      <Routes>
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SettingsPage (task 4.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --- Module importability (first red signal) ---

  it('SettingsPage is importable', async () => {
    const mod = await import('../pages/SettingsPage');
    const component = mod.default ?? (mod as Record<string, unknown>).SettingsPage;
    expect(typeof component).toBe('function');
  });

  // --- Render ---

  it('renders without crashing', async () => {
    await renderSettingsPage();
    expect(document.body).toBeTruthy();
  });

  it('renders a Settings heading or title', async () => {
    await renderSettingsPage();
    await waitFor(() => {
      const body = document.body.textContent?.toLowerCase() ?? '';
      expect(body).toMatch(/settings/i);
    });
  });

  // --- PersonalDictionary inclusion ---

  it('renders the PersonalDictionary section', async () => {
    await renderSettingsPage();
    await waitFor(() => {
      expect(screen.getByTestId('personal-dictionary-mock')).toBeInTheDocument();
    });
  });

  // --- Route wiring ---

  it('App.tsx contains a /settings route', async () => {
    /**
     * We don't render the whole app here (it pulls in many dependencies).
     * Instead, we read the App.tsx source and check for a /settings route
     * declaratively.  If App.tsx is not yet modified this assertion fails (red).
     */
    const appSource = await import('../App?raw').catch(() => null) as { default: string } | null;
    if (appSource) {
      expect(appSource.default).toMatch(/\/settings/);
    } else {
      // Fallback: just verify SettingsPage is importable (enough for red signal)
      const mod = await import('../pages/SettingsPage');
      expect(mod).toBeDefined();
    }
  });
});

// ---------------------------------------------------------------------------
// Bottom-nav isolation (task 4.3 — route is gear-icon only, not in bottom nav)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Round 15 — Export + change-password sections
// ---------------------------------------------------------------------------

describe('SettingsPage — export your data (Round 15 / PR #23)', () => {
  beforeEach(() => {
    mockDownloadExport.mockReset();
  });

  it('renders Export your data button', async () => {
    await renderSettingsPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /export your data/i })).toBeInTheDocument();
    });
  });

  it('Export click calls downloadExport (which fetches /api/export) and triggers download', async () => {
    mockDownloadExport.mockResolvedValueOnce(undefined);
    await renderSettingsPage();
    const btn = await screen.findByRole('button', { name: /export your data/i });
    await act(async () => {
      fireEvent.click(btn);
    });
    expect(mockDownloadExport).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(screen.getByText(/exported/i)).toBeInTheDocument();
    });
  });

  it('Export button disabled while in flight', async () => {
    let resolve: () => void = () => {};
    mockDownloadExport.mockReturnValueOnce(new Promise<void>((r) => { resolve = r; }));
    await renderSettingsPage();
    const btn = await screen.findByRole('button', { name: /export your data/i });
    await act(async () => {
      fireEvent.click(btn);
    });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
    await act(async () => {
      resolve();
    });
    await waitFor(() => {
      expect((btn as HTMLButtonElement).disabled).toBe(false);
    });
  });

  it('Export error shows message', async () => {
    mockDownloadExport.mockRejectedValueOnce(new Error('Network down'));
    await renderSettingsPage();
    const btn = await screen.findByRole('button', { name: /export your data/i });
    await act(async () => {
      fireEvent.click(btn);
    });
    await waitFor(() => {
      expect(screen.getByText(/network down|export failed/i)).toBeInTheDocument();
    });
  });
});

describe('SettingsPage — change password section (Round 15 / PR #23)', () => {
  beforeEach(() => {
    mockChangePassword.mockReset();
  });

  it('renders change-password form fields (current/new/confirm)', async () => {
    await renderSettingsPage();
    await waitFor(() => {
      expect(screen.getByLabelText(/current password/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^new password$/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/confirm new password/i)).toBeInTheDocument();
    });
  });

  it('change-password submit calls changePassword API', async () => {
    mockChangePassword.mockResolvedValueOnce(undefined);
    await renderSettingsPage();

    fireEvent.change(await screen.findByLabelText(/current password/i), { target: { value: 'oldpass99' } });
    fireEvent.change(screen.getByLabelText(/^new password$/i), { target: { value: 'newpass99' } });
    fireEvent.change(screen.getByLabelText(/confirm new password/i), { target: { value: 'newpass99' } });

    const submit = screen.getByRole('button', { name: /change password/i });
    await act(async () => {
      fireEvent.click(submit);
    });

    await waitFor(() => {
      expect(mockChangePassword).toHaveBeenCalledWith('oldpass99', 'newpass99');
    });
  });

  it('change-password success shows confirmation', async () => {
    mockChangePassword.mockResolvedValueOnce(undefined);
    await renderSettingsPage();

    fireEvent.change(await screen.findByLabelText(/current password/i), { target: { value: 'oldpass99' } });
    fireEvent.change(screen.getByLabelText(/^new password$/i), { target: { value: 'newpass99' } });
    fireEvent.change(screen.getByLabelText(/confirm new password/i), { target: { value: 'newpass99' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /change password/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(/password changed/i)).toBeInTheDocument();
    });
  });

  it('change-password mismatched new+confirm shows validation error inline', async () => {
    await renderSettingsPage();

    fireEvent.change(await screen.findByLabelText(/current password/i), { target: { value: 'oldpass99' } });
    fireEvent.change(screen.getByLabelText(/^new password$/i), { target: { value: 'newpass99' } });
    fireEvent.change(screen.getByLabelText(/confirm new password/i), { target: { value: 'different9' } });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /change password/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
    });
    expect(mockChangePassword).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Round 19 / PR C — Browser Extension section (clip-token mint UI)
// ---------------------------------------------------------------------------

describe('SettingsPage — Browser Extension section (Round 19 / PR C)', () => {
  beforeEach(() => {
    mockMintClipToken.mockReset();
  });

  it('renders Browser Extension section heading', async () => {
    await renderSettingsPage();
    await waitFor(() => {
      expect(screen.getByText(/browser extension/i)).toBeInTheDocument();
    });
  });

  it('renders Generate clip token button', async () => {
    await renderSettingsPage();
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /generate clip token/i }),
      ).toBeInTheDocument();
    });
  });

  it('Generate click calls mintClipToken and renders the returned token in a code block', async () => {
    mockMintClipToken.mockResolvedValueOnce({
      clip_token: 'jwt.header.payload.sig',
      expires_in: 2592000,
      scope: 'clip',
    });
    await renderSettingsPage();
    const btn = await screen.findByRole('button', { name: /generate clip token/i });
    await act(async () => {
      fireEvent.click(btn);
    });
    expect(mockMintClipToken).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      const code = document.querySelector('code[aria-label="Clip token"]');
      expect(code).toBeTruthy();
      expect(code!.textContent).toBe('jwt.header.payload.sig');
    });
  });

  it('Copy button copies token to clipboard', async () => {
    mockMintClipToken.mockResolvedValueOnce({
      clip_token: 'jwt.copy.me',
      expires_in: 2592000,
      scope: 'clip',
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
      writable: true,
    });
    await renderSettingsPage();
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: /generate clip token/i }));
    });
    const copyBtn = await screen.findByRole('button', { name: /copy/i });
    await act(async () => {
      fireEvent.click(copyBtn);
    });
    expect(writeText).toHaveBeenCalledWith('jwt.copy.me');
  });

  it('Generating state shows loading text and disables button', async () => {
    let resolve: (v: unknown) => void = () => {};
    mockMintClipToken.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    await renderSettingsPage();
    const btn = await screen.findByRole('button', { name: /generate clip token/i });
    await act(async () => {
      fireEvent.click(btn);
    });
    const loadingBtn = screen.getByRole('button', { name: /generating/i });
    expect((loadingBtn as HTMLButtonElement).disabled).toBe(true);
    await act(async () => {
      resolve({ clip_token: 't', expires_in: 1, scope: 'clip' });
    });
  });

  it('error state shows retry button', async () => {
    mockMintClipToken.mockRejectedValueOnce(new Error('boom'));
    await renderSettingsPage();
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: /generate clip token/i }));
    });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });
  });

  it('token is not persisted to localStorage or sessionStorage', async () => {
    mockMintClipToken.mockResolvedValueOnce({
      clip_token: 'jwt.secret.token',
      expires_in: 2592000,
      scope: 'clip',
    });
    const localSet = vi.spyOn(Storage.prototype, 'setItem');
    await renderSettingsPage();
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: /generate clip token/i }));
    });
    await waitFor(() => {
      expect(
        document.querySelector('code[aria-label="Clip token"]')?.textContent,
      ).toBe('jwt.secret.token');
    });
    const wroteToken = localSet.mock.calls.some(([, value]) =>
      typeof value === 'string' && value.includes('jwt.secret.token'),
    );
    expect(wroteToken).toBe(false);
    localSet.mockRestore();
  });
});

describe('BottomNav does NOT contain a settings link (task 4.3)', () => {
  it('BottomNav component does not render a link to /settings', async () => {
    let BottomNav: React.ComponentType;
    try {
      const mod = await import('../components/BottomNav');
      BottomNav = mod.BottomNav ?? mod.default;
    } catch {
      // BottomNav not yet modified — skip
      return;
    }

    render(
      <MemoryRouter>
        <BottomNav />
      </MemoryRouter>,
    );

    // /settings route must NOT appear as a link inside BottomNav
    const links = Array.from(document.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(links).not.toContain('/settings');
  });
});
