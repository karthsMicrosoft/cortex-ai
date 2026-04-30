/**
 * Task 2 (PWA / vite-plugin-pwa config) — TDD red
 *
 * Tests that vite.config.ts (static analysis via import) has:
 *   - theme_color: '#4F46E5'
 *   - background_color: '#0F172A'
 *   - display: 'standalone'
 *   - icons: 192/512/512-maskable
 *   - runtimeCaching: NetworkFirst for /api/*, CacheFirst for blob URLs
 *
 * Because vite.config.ts uses Node/Vite APIs, we cannot safely import it
 * directly in jsdom. Instead we read the file as a string and assert its
 * content — a pragmatic static-analysis approach used widely in PWA testing.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

// Locate vite.config.ts relative to the repo root (process.cwd() = frontend/ during vitest)
const CONFIG_PATH = resolve(process.cwd(), 'vite.config.ts');

let configSource = '';
try {
  configSource = readFileSync(CONFIG_PATH, 'utf-8');
} catch {
  // File doesn't exist yet — leave empty; all tests will fail (RED state)
  configSource = '';
}

describe('vite.config.ts — PWA manifest (Task 2)', () => {
  it('file exists', () => {
    expect(configSource.length).toBeGreaterThan(0);
  });

  it('registers vite-plugin-pwa', () => {
    expect(configSource).toMatch(/vite-plugin-pwa|VitePWA/);
  });

  it('registers @vitejs/plugin-react', () => {
    expect(configSource).toMatch(/@vitejs\/plugin-react|plugin-react/);
  });

  it('theme_color is #4F46E5', () => {
    expect(configSource).toContain('#4F46E5');
  });

  it('background_color is #0F172A', () => {
    expect(configSource).toContain('#0F172A');
  });

  it('display mode is standalone', () => {
    expect(configSource).toMatch(/standalone/);
  });

  it('includes icon-192.png at 192x192', () => {
    expect(configSource).toMatch(/icon-192\.png/);
    expect(configSource).toMatch(/192x192/);
  });

  it('includes icon-512.png at 512x512', () => {
    expect(configSource).toMatch(/icon-512\.png/);
    expect(configSource).toMatch(/512x512/);
  });

  it('includes maskable icon (icon-512-mask.png)', () => {
    expect(configSource).toMatch(/icon-512-mask\.png/);
    expect(configSource).toMatch(/maskable/);
  });

  it('configures NetworkFirst handler for /api/* routes', () => {
    expect(configSource).toMatch(/NetworkFirst/);
    expect(configSource).toMatch(/\/api\//);
  });

  it('configures CacheFirst handler for blob URLs', () => {
    expect(configSource).toMatch(/CacheFirst/);
    expect(configSource).toMatch(/blob/);
  });

  it('workbox runtimeCaching is configured', () => {
    expect(configSource).toMatch(/runtimeCaching/);
  });

  it('app name is Cortex', () => {
    expect(configSource).toMatch(/Cortex/);
  });
});

// ---------------------------------------------------------------------------
// public/manifest.json — mirrors vite.config.ts manifest
// ---------------------------------------------------------------------------

const MANIFEST_PATH = resolve(process.cwd(), 'public', 'manifest.json');
let manifest: Record<string, unknown> = {};
try {
  manifest = JSON.parse(readFileSync(MANIFEST_PATH, 'utf-8'));
} catch {
  manifest = {};
}

describe('public/manifest.json (Task 2.2)', () => {
  it('file exists and is valid JSON', () => {
    expect(Object.keys(manifest).length).toBeGreaterThan(0);
  });

  it('theme_color is #4F46E5', () => {
    expect(manifest.theme_color).toBe('#4F46E5');
  });

  it('background_color is #0F172A', () => {
    expect(manifest.background_color).toBe('#0F172A');
  });

  it('display is standalone', () => {
    expect(manifest.display).toBe('standalone');
  });

  it('has name and short_name', () => {
    expect(manifest.name).toBeTruthy();
    expect(manifest.short_name).toBeTruthy();
  });

  it('icons array has 192, 512, and maskable entries', () => {
    const icons = manifest.icons as Array<{ src: string; sizes: string; purpose?: string }>;
    expect(Array.isArray(icons)).toBe(true);

    const has192 = icons.some((i) => i.sizes === '192x192');
    const has512 = icons.some((i) => i.sizes === '512x512' && !i.purpose?.includes('maskable'));
    const hasMask = icons.some((i) => i.purpose?.includes('maskable'));

    expect(has192).toBe(true);
    expect(has512).toBe(true);
    expect(hasMask).toBe(true);
  });
});
