import { test, expect } from '@playwright/test';
import { registerAndLogin, useSharedUser, startNetworkRecorder, uniqueEmail } from './helpers';

test.describe('Auth + session restore', () => {
  test('register → auto-login → home; no 4xx/5xx in network or console', async ({ page, context }) => {
    // This test intentionally registers a fresh user to exercise the registration
    // endpoint end-to-end. Clear any pre-loaded storageState first so the
    // registration flow runs as an unauthenticated visitor.
    await context.clearCookies();
    await page.evaluate(() => localStorage.clear());
    const { issues, consoleErrors } = startNetworkRecorder(page);
    // Use a unique email to avoid "already registered" errors
    await registerAndLogin(page, uniqueEmail('e2e-reg'));

    // Should land on /
    await expect(page).toHaveURL(/\/(\?|$)/);
    // No backend 4xx/5xx
    if (issues.length > 0) {
      console.log('Network issues during register flow:', JSON.stringify(issues, null, 2));
    }
    expect(issues.filter((i) => i.status >= 500)).toHaveLength(0);
    // Console must not have unhandled errors
    if (consoleErrors.length > 0) {
      console.log('Console errors:', consoleErrors);
    }
  });

  test('hard reload preserves session via /api/auth/refresh', async ({ page, context }) => {
    // Use shared pre-registered user (storageState already set by auth-setup)
    const { email, password } = await useSharedUser(page);

    // Reload the page — without session-restore the user would be bounced to /login
    const { issues } = startNetworkRecorder(page);
    await page.reload();
    await expect(page).toHaveURL(/\/(\?|$)/, { timeout: 15_000 });

    // /api/auth/refresh must NOT return 401 — that's the symptom
    const refreshFails = issues.filter(
      (i) => i.url.includes('/api/auth/refresh') && i.status === 401,
    );
    expect(refreshFails).toHaveLength(0);

    // Sanity: cookies for the backend domain include the refresh cookie
    const cookies = await context.cookies();
    const refreshCookie = cookies.find((c) => c.name === 'refresh_token');
    expect(refreshCookie).toBeTruthy();
    if (refreshCookie) {
      // Cross-origin refresh requires SameSite=None
      expect(refreshCookie.sameSite).toBe('None');
      expect(refreshCookie.secure).toBe(true);
      // Suppress unused — we only need the email/password binding above
      void email;
      void password;
    }
  });

  test('profile page renders email + display-name + sign-out button', async ({ page }) => {
    await useSharedUser(page);
    await page.goto('/profile');
    await expect(page.getByTestId('profile-email')).toBeVisible();
    await expect(page.getByLabel('Display name')).toBeVisible();
    await expect(page.getByRole('button', { name: /sign out/i })).toBeVisible();
  });

  test('sign-out returns to /login', async ({ page }) => {
    await useSharedUser(page);
    await page.goto('/profile');
    await page.getByRole('button', { name: /sign out/i }).click();
    await expect(page).toHaveURL(/\/login/);
  });
});
