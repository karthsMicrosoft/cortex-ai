import { test, expect } from '@playwright/test';
import { useSharedUser, startNetworkRecorder } from './helpers';

test.describe('Voice capture (fake media stream)', () => {
  test('FAB tap → recording starts → stop → /api/voice/upload not 422', async ({ page }) => {
    const { issues, consoleErrors } = startNetworkRecorder(page);
    await useSharedUser(page);

    await page.goto('/');

    // Find the mic FAB by aria-label
    const fab = page.getByRole('button', { name: /start recording/i });
    await expect(fab).toBeVisible({ timeout: 10_000 });

    await fab.click();
    // Should switch to MicOff variant after a short moment
    await expect(page.getByRole('button', { name: /stop recording/i })).toBeVisible({ timeout: 5_000 });

    // Record for a couple seconds
    await page.waitForTimeout(2_500);

    // Stop
    await page.getByRole('button', { name: /stop recording/i }).click();

    // Wait for upload + redirect
    await page.waitForTimeout(6_000);

    // /api/voice/upload must NOT return 422 — that's the form-field-name bug
    const fieldNameBugs = issues.filter(
      (i) => i.url.endsWith('/api/voice/upload') && i.status === 422,
    );
    expect(fieldNameBugs, JSON.stringify(fieldNameBugs)).toHaveLength(0);

    // /api/upload must NOT return 500 — embedding/blob storage regression
    const upload500 = issues.filter(
      (i) => i.url.endsWith('/api/upload') && i.status === 500,
    );
    expect(upload500, JSON.stringify(upload500)).toHaveLength(0);

    // No CORS errors in console
    const corsErrors = consoleErrors.filter((e) => /CORS|Access-Control/i.test(e));
    expect(corsErrors, JSON.stringify(corsErrors)).toHaveLength(0);
  });
});
