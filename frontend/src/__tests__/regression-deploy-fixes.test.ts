/**
 * Regression tests for production bugs found during the live-deploy smoke
 * test on 2026-04-30 / 2026-05-01.
 *
 * Bugs covered:
 *  R1. apiUrl()/wsUrl() helpers in api/client.ts
 *  R2. syncManager.ts uses apiUrl() for all fetch calls
 *      (was: raw fetch('/api/...') -> 404 from SWA host)
 *  R3. VoiceCapture.tsx uses wsUrl() + apiUrl() for WS / uploads
 *      (was: _wsBaseUrl() -> wss://SWA -> 405)
 *  R4. ShadowReaderPrompt.tsx uses apiUrl() for voice-answer upload
 *  R5. staticwebapp.config.json declares Permissions-Policy: microphone=(self)
 *      so iOS Safari + Android Chrome don't refuse the mic prompt
 *  R6. LoginPage / RegisterPage call setAccessToken BEFORE me()
 *      (was: 401 because /me had no Authorization header)
 *
 * These are guard rails — if a future refactor reverts any of them, the
 * symptom won't reach production.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

// -------------------------------------------------------------------------
// Helper: read a file from the project tree (relative to frontend/)
// -------------------------------------------------------------------------
const FRONTEND_ROOT = resolve(__dirname, '..', '..');
function readSrc(relativePath: string): string {
  const full = resolve(FRONTEND_ROOT, relativePath);
  if (!existsSync(full)) {
    throw new Error(`Source file not found: ${relativePath}`);
  }
  return readFileSync(full, 'utf-8');
}

// =========================================================================
// R1 — apiUrl / wsUrl helpers
// =========================================================================

describe('R1: api/client.ts URL helpers', () => {
  beforeEach(() => {
    vi.resetModules();
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('apiUrl resolves a relative /api/* path against VITE_API_BASE_URL', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://cortexks-api.example.com');
    const { apiUrl } = await import('../api/client');
    expect(apiUrl('/api/notes')).toBe('https://cortexks-api.example.com/api/notes');
  });

  it('apiUrl strips a trailing slash on the base before joining', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://cortexks-api.example.com/');
    const { apiUrl } = await import('../api/client');
    expect(apiUrl('/api/notes')).toBe('https://cortexks-api.example.com/api/notes');
  });

  it('apiUrl prepends a slash if the path is missing one', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://cortexks-api.example.com');
    const { apiUrl } = await import('../api/client');
    expect(apiUrl('api/notes')).toBe('https://cortexks-api.example.com/api/notes');
  });

  it('apiUrl leaves an absolute https URL unchanged', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://cortexks-api.example.com');
    const { apiUrl } = await import('../api/client');
    expect(apiUrl('https://other.example.com/api/x')).toBe(
      'https://other.example.com/api/x'
    );
  });

  it('apiUrl returns the raw path when VITE_API_BASE_URL is empty (dev fallback)', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '');
    const { apiUrl } = await import('../api/client');
    expect(apiUrl('/api/notes')).toBe('/api/notes');
  });

  it('wsUrl converts https base -> wss', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://cortexks-api.example.com');
    const { wsUrl } = await import('../api/client');
    expect(wsUrl('/api/voice/stream?token=abc')).toBe(
      'wss://cortexks-api.example.com/api/voice/stream?token=abc'
    );
  });

  it('wsUrl converts http base -> ws (dev)', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000');
    const { wsUrl } = await import('../api/client');
    expect(wsUrl('/api/voice/stream')).toBe('ws://localhost:8000/api/voice/stream');
  });

  it('wsUrl falls back to window.location.host when VITE_API_BASE_URL is empty', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '');
    // jsdom default: http://localhost:3000 — but that varies; test the SHAPE
    const { wsUrl } = await import('../api/client');
    const out = wsUrl('/api/voice/stream');
    expect(out).toMatch(/^wss?:\/\/[^/]+\/api\/voice\/stream$/);
  });

  it('wsUrl prepends a leading slash if the path is missing one', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://cortexks-api.example.com');
    const { wsUrl } = await import('../api/client');
    expect(wsUrl('api/voice/stream')).toBe(
      'wss://cortexks-api.example.com/api/voice/stream'
    );
  });
});

// =========================================================================
// R2 — syncManager.ts uses apiUrl()
// =========================================================================

describe('R2: syncManager.ts uses apiUrl() for absolute backend URLs', () => {
  const src = readSrc('src/sync/syncManager.ts');

  it('imports apiUrl from api/client', () => {
    expect(src).toMatch(/import\s*\{\s*apiUrl\s*\}\s*from\s*['"]\.\.\/api\/client['"]/);
  });

  it('does NOT contain raw fetch(\'/api/...\') with relative path', () => {
    // After the fix every fetch is `fetch(apiUrl(...), ...)`.
    // A bare `fetch('/api/...'` would re-introduce the SWA-host bug.
    expect(src).not.toMatch(/fetch\s*\(\s*['"`]\/api\//);
  });

  it('wraps /api/upload, /api/notes, /api/sync/pull, /api/notes/{id} with apiUrl()', () => {
    expect(src).toMatch(/fetch\s*\(\s*apiUrl\s*\(\s*['"`]\/api\/upload['"`]\s*\)/);
    expect(src).toMatch(/fetch\s*\(\s*apiUrl\s*\(\s*['"`]\/api\/notes['"`]\s*\)/);
    expect(src).toMatch(/fetch\s*\(\s*apiUrl\s*\(\s*[`]\/api\/sync\/pull/);
    expect(src).toMatch(/fetch\s*\(\s*apiUrl\s*\(\s*[`]\/api\/notes\/\$\{id\}/);
  });
});

// =========================================================================
// R3 — VoiceCapture.tsx uses wsUrl() + apiUrl()
// =========================================================================

describe('R3: VoiceCapture.tsx uses wsUrl() + apiUrl()', () => {
  const src = readSrc('src/components/VoiceCapture.tsx');

  it('imports apiUrl + wsUrl from api/client', () => {
    expect(src).toMatch(/import\s*\{[^}]*\bapiUrl\b[^}]*\}\s*from\s*['"]\.\.\/api\/client['"]/);
    expect(src).toMatch(/import\s*\{[^}]*\bwsUrl\b[^}]*\}\s*from\s*['"]\.\.\/api\/client['"]/);
  });

  it('does NOT define _wsBaseUrl() (replaced by wsUrl helper)', () => {
    expect(src).not.toMatch(/function\s+_wsBaseUrl/);
  });

  it('does NOT build the WS URL from window.location.host', () => {
    // The bug was: `${proto}//${window.location.host}/api/voice/stream` -> SWA host
    expect(src).not.toMatch(/window\.location\.host[^.]*\/api\/voice\/stream/);
  });

  it('opens the WebSocket via wsUrl(`/api/voice/stream?token=...`)', () => {
    expect(src).toMatch(/wsUrl\s*\(\s*[`'"]\/api\/voice\/stream\?token=/);
  });

  it('uploadBlob uses apiUrl(\'/api/upload\') (not relative)', () => {
    expect(src).toMatch(/fetch\s*\(\s*apiUrl\s*\(\s*['"]\/api\/upload['"]/);
    expect(src).not.toMatch(/fetch\s*\(\s*['"]\/api\/upload['"]/);
  });

  it('uploadVoice uses apiUrl(\'/api/voice/upload\') (not relative)', () => {
    expect(src).toMatch(/fetch\s*\(\s*apiUrl\s*\(\s*['"]\/api\/voice\/upload['"]/);
    expect(src).not.toMatch(/fetch\s*\(\s*['"]\/api\/voice\/upload['"]/);
  });
});

// =========================================================================
// R4 — ShadowReaderPrompt.tsx uses apiUrl()
// =========================================================================

describe('R4: ShadowReaderPrompt voice-answer upload (feature removed)', () => {
  // The voice-mic answer + audio-upload path was removed from
  // ShadowReaderPrompt — the bottom-sheet now accepts text answers only.
  // The R4 invariant we still want to guard is: the component must NOT
  // ship a relative fetch('/api/upload/audio') path that would hit the
  // SWA host instead of the API host. The "wraps with apiUrl()" assertion
  // was about a since-removed codepath; converted to a removal-guard.
  // (The component's docstring still mentions /api/upload/audio for
  // historical context — that's fine, what matters is no runtime fetch.)
  const src = readSrc('src/components/ShadowReaderPrompt.tsx');

  it('does NOT call fetch with a relative /api/upload/audio path', () => {
    expect(src).not.toMatch(/fetch\s*\(\s*['"]\/api\/upload\/audio['"]/);
  });

  it('does NOT call fetch with apiUrl(/api/upload/audio) either (feature removed)', () => {
    // If voice answer comes back, restore both this test and the original
    // "wraps with apiUrl" expectation.
    expect(src).not.toMatch(/fetch\s*\(\s*apiUrl\s*\(\s*['"]\/api\/upload\/audio['"]/);
  });
});

// =========================================================================
// R5 — staticwebapp.config.json Permissions-Policy header
// =========================================================================

describe('R5: staticwebapp.config.json declares mic + camera Permissions-Policy', () => {
  const raw = readSrc('public/staticwebapp.config.json');
  const config = JSON.parse(raw) as {
    globalHeaders?: Record<string, string>;
    routes?: unknown;
    navigationFallback?: unknown;
  };

  it('has a globalHeaders block', () => {
    expect(config.globalHeaders).toBeDefined();
  });

  it('grants microphone=(self) so iOS Safari / Android Chrome will prompt', () => {
    const policy = config.globalHeaders?.['Permissions-Policy'] ?? '';
    expect(policy).toMatch(/microphone\s*=\s*\(\s*self\s*\)/);
  });

  it('grants camera=(self) for image capture from device camera', () => {
    const policy = config.globalHeaders?.['Permissions-Policy'] ?? '';
    expect(policy).toMatch(/camera\s*=\s*\(\s*self\s*\)/);
  });

  it('does NOT proxy /api/* (avoid POST-body-stripping 405 bug)', () => {
    // The proxy rewrite was removed because SWA strips POST bodies when the
    // rewrite target is an external URL. Frontend now uses absolute backend
    // URLs via VITE_API_BASE_URL instead.
    const routes = (config.routes ?? []) as Array<{ route?: string; rewrite?: string }>;
    for (const r of routes) {
      if (r.route === '/api/*' && r.rewrite) {
        throw new Error(
          `staticwebapp.config.json must not proxy /api/* — found rewrite to ${r.rewrite}`
        );
      }
    }
  });

  it('keeps SPA navigationFallback so deep links don\'t 404', () => {
    expect(config.navigationFallback).toBeDefined();
  });
});

// =========================================================================
// R6 — LoginPage / RegisterPage call setAccessToken BEFORE me()
// =========================================================================

describe('R6: Login/Register set the access token BEFORE awaiting me()', () => {
  // The bug: calling `me()` before `useAuthStore.getState().setAccessToken(...)`
  // meant fetchWithAuth read the still-null token and `/api/auth/me` came back
  // 401. We assert the order at the source level — a static check is the
  // simplest way to keep the fix from regressing.

  it('LoginPage stores access_token before calling me()', () => {
    const src = readSrc('src/pages/LoginPage.tsx');
    const setAccessTokenIdx = src.indexOf('setAccessToken(data.access_token)');
    const meCallIdx = src.indexOf('await me()');
    expect(setAccessTokenIdx).toBeGreaterThan(-1);
    expect(meCallIdx).toBeGreaterThan(-1);
    expect(setAccessTokenIdx).toBeLessThan(meCallIdx);
  });

  it('RegisterPage stores access_token before calling me()', () => {
    const src = readSrc('src/pages/RegisterPage.tsx');
    // Round-7: production uses ``regData.access_token`` (the variable name for
    // the register-response object) rather than the ``data.access_token`` shape
    // used by login. Match either to keep the regression guard meaningful.
    const setAccessTokenIdx = Math.max(
      src.indexOf('setAccessToken(regData.access_token)'),
      src.indexOf('setAccessToken(data.access_token)'),
    );
    const meCallIdx = src.indexOf('await me()');
    expect(setAccessTokenIdx).toBeGreaterThan(-1);
    expect(meCallIdx).toBeGreaterThan(-1);
    expect(setAccessTokenIdx).toBeLessThan(meCallIdx);
  });
});
