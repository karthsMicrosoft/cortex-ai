import { test, expect } from '@playwright/test';
import { useSharedUser, startNetworkRecorder } from './helpers';

test.describe('Smoke navigation — every protected route loads without 500', () => {
  const protectedRoutes = ['/', '/library', '/search', '/insights', '/create', '/conflicts', '/settings', '/profile'];

  for (const route of protectedRoutes) {
    test(`${route} loads without 5xx + no console errors`, async ({ page }) => {
      const { issues, consoleErrors } = startNetworkRecorder(page);
      await useSharedUser(page);
      await page.goto(route);
      // Allow async data fetches to finish
      await page.waitForTimeout(3_000);

      const fiveHundreds = issues.filter((i) => i.status >= 500);
      expect(
        fiveHundreds,
        `5xx on ${route}: ${JSON.stringify(fiveHundreds, null, 2)}`,
      ).toHaveLength(0);

      const corsErrors = consoleErrors.filter((e) => /CORS|Access-Control/i.test(e));
      expect(
        corsErrors,
        `CORS errors on ${route}: ${JSON.stringify(corsErrors, null, 2)}`,
      ).toHaveLength(0);
    });
  }
});
