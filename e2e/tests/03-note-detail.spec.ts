import { test, expect } from '@playwright/test';
import { useSharedUser, startNetworkRecorder } from './helpers';

test.describe('Note detail navigation', () => {
  test('clicking a note in Library opens detail without 404', async ({ page }) => {
    const { issues } = startNetworkRecorder(page);
    await useSharedUser(page);

    await page.goto('/');
    const textArea = page.locator('textarea, input[type="text"]').first();
    await expect(textArea).toBeVisible({ timeout: 10_000 });
    const sample = `Detail nav test ${Date.now()}`;
    await textArea.fill(sample);
    await page.getByRole('button', { name: /save|submit|send|capture/i }).first().click();

    await expect(page).toHaveURL(/\/library/, { timeout: 10_000 });
    await expect(page.getByText(sample, { exact: false })).toBeVisible({ timeout: 15_000 });

    // Wait for sync to assign serverId
    await page.waitForTimeout(4_000);

    // Click the note
    await page.getByText(sample, { exact: false }).first().click();
    await expect(page).toHaveURL(/\/note\//, { timeout: 5_000 });

    // /api/notes/{id} must NOT 404 — that's the symptom of using localId
    const notFound = issues.filter(
      (i) => /\/api\/notes\/[\w-]+$/.test(i.url) && i.status === 404,
    );
    expect(notFound, JSON.stringify(notFound)).toHaveLength(0);

    const similarNotFound = issues.filter(
      (i) => /\/api\/search\/similar\//.test(i.url) && i.status === 404,
    );
    expect(similarNotFound, JSON.stringify(similarNotFound)).toHaveLength(0);
  });
});
