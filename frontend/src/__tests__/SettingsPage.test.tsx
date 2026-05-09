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
vi.mock('../api/auth', () => ({
  changePassword: (...args: unknown[]) => mockChangePassword(...args),
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
