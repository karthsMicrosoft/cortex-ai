/**
 * Phase 5 / PR 5.1 — manifest share_target
 *
 * Verifies that public/manifest.json declares a share_target so iOS and
 * Android share sheets can dispatch text/URL payloads into the installed
 * Cortex PWA. Also asserts vite-plugin-pwa's manifest mirrors it (so the
 * generated manifest at build time also carries share_target).
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const MANIFEST_PATH = resolve(process.cwd(), 'public', 'manifest.json');
const VITE_CONFIG_PATH = resolve(process.cwd(), 'vite.config.ts');

let manifest: Record<string, unknown> = {};
try {
  manifest = JSON.parse(readFileSync(MANIFEST_PATH, 'utf-8'));
} catch {
  manifest = {};
}

let viteConfigSource = '';
try {
  viteConfigSource = readFileSync(VITE_CONFIG_PATH, 'utf-8');
} catch {
  viteConfigSource = '';
}

interface ShareTarget {
  action?: string;
  method?: string;
  params?: Record<string, string>;
}

describe('public/manifest.json — share_target (Phase 5 / PR 5.1)', () => {
  it('declares a share_target block', () => {
    expect(manifest.share_target).toBeTruthy();
  });

  it('share_target.action points to /share', () => {
    const st = manifest.share_target as ShareTarget;
    expect(st.action).toBe('/share');
  });

  it('share_target.method is GET (URL-param contract)', () => {
    const st = manifest.share_target as ShareTarget;
    expect((st.method ?? '').toUpperCase()).toBe('GET');
  });

  it('share_target.params maps title, text, and url', () => {
    const st = manifest.share_target as ShareTarget;
    expect(st.params).toBeTruthy();
    expect(st.params?.title).toBe('title');
    expect(st.params?.text).toBe('text');
    expect(st.params?.url).toBe('url');
  });
});

describe('vite.config.ts — share_target mirrors public/manifest.json', () => {
  it('vite.config.ts contains a share_target block', () => {
    expect(viteConfigSource).toMatch(/share_target/);
  });

  it("vite.config.ts share_target.action is '/share'", () => {
    expect(viteConfigSource).toMatch(/action:\s*['"]\/share['"]/);
  });
});
