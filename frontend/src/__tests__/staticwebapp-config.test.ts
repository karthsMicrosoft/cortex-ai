/**
 * Round 20 / PR delta — staticwebapp.config.json CSP + security headers.
 *
 * Static-introspection test: parses frontend/public/staticwebapp.config.json
 * and asserts the strict CSP, Permissions-Policy, and supporting headers
 * are configured. Azure Static Web Apps serves the SPA assets, so these
 * headers — not the FastAPI middleware — protect the frontend bundle.
 *
 * Tied to DECISIONS § 22v: a strict CSP is the mitigation that closes
 * the XSS gap created by storing the refresh token in localStorage.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const CONFIG_PATH = resolve(process.cwd(), 'public', 'staticwebapp.config.json');
const API_ORIGIN = 'https://cortexks-api.wonderfulpond-177bdc9c.centralus.azurecontainerapps.io';

let raw = '';
let config: Record<string, any> = {};
let parseError: Error | null = null;
try {
  raw = readFileSync(CONFIG_PATH, 'utf-8');
  config = JSON.parse(raw);
} catch (err) {
  parseError = err as Error;
}

function csp(): string {
  const headers = (config.globalHeaders ?? {}) as Record<string, string>;
  return headers['Content-Security-Policy'] ?? '';
}

function directive(name: string): string {
  const policy = csp();
  // Split on ";" and find the directive starting with `name `
  const parts = policy.split(';').map((p) => p.trim()).filter(Boolean);
  const match = parts.find((p) => p === name || p.startsWith(name + ' '));
  return match ?? '';
}

describe('staticwebapp.config.json — CSP + security headers (Round 20 / PR delta)', () => {
  it('parses as valid JSON', () => {
    expect(parseError).toBeNull();
    expect(typeof config).toBe('object');
  });

  it("globalHeaders.Content-Security-Policy contains default-src 'self'", () => {
    expect(directive('default-src')).toContain("'self'");
  });

  it("Content-Security-Policy disallows inline scripts (no 'unsafe-inline' in script-src)", () => {
    const scriptSrc = directive('script-src');
    expect(scriptSrc).not.toContain("'unsafe-inline'");
    expect(scriptSrc).toContain("'self'");
  });

  it('Content-Security-Policy includes the API origin in connect-src (https + wss)', () => {
    const connect = directive('connect-src');
    expect(connect).toContain(API_ORIGIN);
    expect(connect).toContain(`wss://${API_ORIGIN.replace(/^https:\/\//, '')}`);
  });

  it("frame-ancestors directive blocks all iframes ('none')", () => {
    expect(directive('frame-ancestors')).toBe("frame-ancestors 'none'");
  });

  it('Content-Security-Policy upgrades insecure requests', () => {
    expect(csp()).toMatch(/upgrade-insecure-requests/);
  });

  it("object-src is 'none'", () => {
    expect(directive('object-src')).toBe("object-src 'none'");
  });

  it('Permissions-Policy denies geolocation', () => {
    const pp = (config.globalHeaders ?? {})['Permissions-Policy'] ?? '';
    expect(pp).toMatch(/geolocation=\(\)/);
  });

  it('Permissions-Policy allows camera + microphone from self only', () => {
    const pp = (config.globalHeaders ?? {})['Permissions-Policy'] ?? '';
    expect(pp).toMatch(/camera=\(self\)/);
    expect(pp).toMatch(/microphone=\(self\)/);
  });

  it('X-Content-Type-Options remains nosniff', () => {
    const headers = (config.globalHeaders ?? {}) as Record<string, string>;
    expect(headers['X-Content-Type-Options']).toBe('nosniff');
  });
});

// ---------------------------------------------------------------------------
// Round 30 — Azure Blob audio playback regression
//
// The Round 20 CSP omitted a `media-src` directive, which silently fell
// back to `default-src 'self'` and blocked every `<audio>` (and WaveSurfer
// internal fetch) for Azure Blob SAS URLs. Voice notes uploaded fine and
// transcribed fine, but the player on Note Detail threw a CSP error. The
// fix adds media-src + extends connect-src + adds the blob: scheme to
// img-src for offline image previews. These tests pin the contract so a
// future CSP tightening can't silently re-break voice playback.
// ---------------------------------------------------------------------------

describe('staticwebapp.config.json — Round 30 media + blob CSP', () => {
  const BLOB_HOST = 'https://*.blob.core.windows.net';

  it('media-src directive is set (otherwise it falls back to default-src and blocks <audio>)', () => {
    expect(directive('media-src')).not.toBe('');
  });

  it("media-src allows 'self', blob:, and Azure Blob (https://*.blob.core.windows.net)", () => {
    const media = directive('media-src');
    expect(media).toContain("'self'");
    expect(media).toContain('blob:');
    expect(media).toContain(BLOB_HOST);
  });

  it('connect-src includes Azure Blob so WaveSurfer fetch() can load audio bytes', () => {
    expect(directive('connect-src')).toContain(BLOB_HOST);
  });

  it('img-src includes blob: scheme for offline image previews (URL.createObjectURL)', () => {
    expect(directive('img-src')).toContain('blob:');
  });

  it('img-src still allows Azure Blob (https://*.blob.core.windows.net)', () => {
    expect(directive('img-src')).toContain(BLOB_HOST);
  });
});
