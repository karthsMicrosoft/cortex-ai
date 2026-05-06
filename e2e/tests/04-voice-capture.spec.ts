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

    // /api/voice/upload must NOT return 422 with the form-field-name bug
    // signature. The chromium fake media stream produces invalid webm bytes
    // that Azure Speech rejects, so a 422 with a "Could not transcribe"
    // detail is acceptable; only the OLD 422 ("Field required: body.file")
    // should fail this test.
    const fieldNameBugs = issues.filter((i) => {
      if (!i.url.endsWith('/api/voice/upload') || i.status !== 422) return false;
      const body = i.body ?? '';
      return /Field required.*body\.file|"loc":\["body","file"\]/i.test(body);
    });
    expect(fieldNameBugs, JSON.stringify(fieldNameBugs)).toHaveLength(0);

    // /api/upload must NOT return 500 — embedding/blob storage regression
    const upload500 = issues.filter(
      (i) => i.url.endsWith('/api/upload') && i.status === 500,
    );
    expect(upload500, JSON.stringify(upload500)).toHaveLength(0);

    // /api/voice/upload must also NOT return 500. A 422 from invalid fake
    // audio (chromium synthetic stream isn't a valid webm) is acceptable.
    const voice500 = issues.filter(
      (i) => i.url.endsWith('/api/voice/upload') && i.status === 500,
    );
    expect(voice500, JSON.stringify(voice500)).toHaveLength(0);

    // No CORS errors in console (any 500 strips CORSMiddleware response
    // headers — this assertion catches that regression even if we missed
    // the specific 5xx above).
    const corsErrors = consoleErrors.filter((e) => /CORS|Access-Control/i.test(e));
    expect(corsErrors, JSON.stringify(corsErrors)).toHaveLength(0);
  });
});
