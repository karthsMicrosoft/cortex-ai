import { expect, type Page, type Request, type Response } from '@playwright/test';
import { SHARED_EMAIL, SHARED_PASSWORD } from './constants';

export const BACKEND_URL = 'https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io';
export const FRONTEND_URL = 'https://gentle-river-06c1e4e10.7.azurestaticapps.net';

/**
 * Generate a fresh user email so each test run uses a clean account
 * (the live DB is shared, so we never reuse an email between runs).
 */
export function uniqueEmail(prefix = 'e2e'): string {
  const stamp = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  return `${prefix}+${stamp}@example.com`;
}

/** Capture every API call + response, surface 4xx/5xx as named issues. */
export interface NetworkIssue {
  url: string;
  method: string;
  status: number;
  body?: string;
}

export function startNetworkRecorder(page: Page): { issues: NetworkIssue[]; consoleErrors: string[] } {
  const issues: NetworkIssue[] = [];
  const consoleErrors: string[] = [];

  page.on('response', async (resp: Response) => {
    const req: Request = resp.request();
    const url = resp.url();
    if (!url.includes(BACKEND_URL.replace(/^https?:\/\//, ''))) return;
    const status = resp.status();
    if (status >= 400) {
      let body = '';
      try {
        body = await resp.text();
      } catch {
        // body already consumed
      }
      issues.push({ url, method: req.method(), status, body: body.slice(0, 500) });
    }
  });

  page.on('console', (msg) => {
    const text = msg.text();
    if (msg.type() === 'error') {
      consoleErrors.push(text);
    }
  });

  page.on('pageerror', (err) => {
    consoleErrors.push(`pageerror: ${err.message}`);
  });

  return { issues, consoleErrors };
}

export async function registerAndLogin(
  page: Page,
  email = uniqueEmail(),
  password = 'TestPass123*',
  displayName = 'E2E User',
): Promise<{ email: string; password: string }> {
  await page.goto('/register');
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  // displayName field is optional and may be present
  const nameInput = page.locator('input[autocomplete="name"]');
  if (await nameInput.count()) {
    await nameInput.fill(displayName);
  }
  await page.getByRole('button', { name: /create account|register|sign up/i }).click();
  // After successful auto-login the URL goes to /
  await expect(page).toHaveURL(/\/(\?|$)/, { timeout: 20_000 });
  return { email, password };
}

export async function loginExisting(
  page: Page,
  email: string,
  password: string,
): Promise<void> {
  await page.goto('/login');
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole('button', { name: /sign in|log in|login/i }).click();
  await expect(page).toHaveURL(/\/(\?|$)/, { timeout: 20_000 });
}

/**
 * Restore the shared pre-registered session (used by most tests).
 * Because the chromium-desktop project has storageState set, the browser
 * context is already authenticated. This function simply navigates to /
 * and confirms the redirect did NOT end up at /login or /register.
 *
 * Returns the shared email so tests that need to assert on it can do so.
 */
export async function useSharedUser(page: Page): Promise<{ email: string; password: string }> {
  await page.goto('/');
  // Wait briefly for any auth redirect to settle before checking URL
  await page.waitForTimeout(1_000);
  // If the storageState is valid the app stays on / (or redirects to / from any
  // protected sub-path). If for any reason we land on login, fall back to
  // explicit login with the shared credentials.
  const url = page.url();
  if (/\/(login|register)/.test(url)) {
    await loginExisting(page, SHARED_EMAIL, SHARED_PASSWORD);
  }
  await expect(page).toHaveURL(/\/(\?|$)/, { timeout: 20_000 });
  return { email: SHARED_EMAIL, password: SHARED_PASSWORD };
}
