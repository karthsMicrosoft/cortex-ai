import { defineConfig, devices } from '@playwright/test';
import * as path from 'path';

// Storage state written by auth.setup.ts and consumed by all chromium-desktop tests.
const AUTH_FILE = path.join(__dirname, '.auth', 'user.json');

export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 1,
  reporter: [['list'], ['json', { outputFile: 'test-results.json' }]],
  use: {
    baseURL: 'https://gentle-river-06c1e4e10.7.azurestaticapps.net',
    headless: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    permissions: ['microphone', 'camera'],
    // Browser-level grants — Cortex needs mic + camera even though our tests
    // mock the actual audio stream below.
  },
  projects: [
    // ── 1. Auth setup: registers once and writes .auth/user.json ──────────
    {
      name: 'auth-setup',
      testMatch: /auth\.setup\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          args: [
            '--use-fake-ui-for-media-stream',
            '--use-fake-device-for-media-stream',
          ],
        },
      },
    },

    // ── 2. All real tests: restore the shared session ─────────────────────
    {
      name: 'chromium-desktop',
      dependencies: ['auth-setup'],
      use: {
        ...devices['Desktop Chrome'],
        storageState: AUTH_FILE,
        launchOptions: {
          args: [
            '--use-fake-ui-for-media-stream',
            '--use-fake-device-for-media-stream',
            // No real mic input — fake stream returns deterministic silent audio
          ],
        },
      },
    },
  ],
});
