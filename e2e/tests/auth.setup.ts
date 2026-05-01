/**
 * auth.setup.ts — runs once before all chromium-desktop tests.
 *
 * Registers the shared E2E account (or logs in if already registered) and
 * saves browser storage state to .auth/user.json so every test can restore
 * an authenticated session without hitting /register on each test.
 *
 * The file is gitignored (.auth/ should be in .gitignore) and regenerated
 * on each CI run / local re-run.
 */
import { test as setup, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { AUTH_FILE, SHARED_EMAIL, SHARED_PASSWORD } from './constants';

setup('register shared e2e user', async ({ page }) => {
  // Ensure .auth directory exists
  const authDir = path.dirname(AUTH_FILE);
  if (!fs.existsSync(authDir)) {
    fs.mkdirSync(authDir, { recursive: true });
  }

  // Attempt registration first
  await page.goto('/register');

  // Fill display name if present
  const nameInput = page.locator('input[autocomplete="name"]');
  if (await nameInput.count()) {
    await nameInput.fill('E2E Shared');
  }

  await page.locator('input[type="email"]').fill(SHARED_EMAIL);
  await page.locator('input[type="password"]').fill(SHARED_PASSWORD);
  await page.getByRole('button', { name: /create account|register|sign up/i }).click();

  // Wait briefly to see if registration succeeded or failed
  await page.waitForTimeout(3_000);

  const currentUrl = page.url();

  if (/\/(login|register)/.test(currentUrl)) {
    // Registration may have failed (e.g., user already exists or rate-limited).
    // Fall back to login with existing credentials.
    await page.goto('/login');
    await page.locator('input[type="email"]').fill(SHARED_EMAIL);
    await page.locator('input[type="password"]').fill(SHARED_PASSWORD);
    await page.getByRole('button', { name: /sign in|log in|login/i }).click();
  }

  // Wait for redirect to /
  await expect(page).toHaveURL(/\/(\?|$)/, { timeout: 30_000 });

  // Save storage state (cookies + localStorage) for reuse
  await page.context().storageState({ path: AUTH_FILE });
});
