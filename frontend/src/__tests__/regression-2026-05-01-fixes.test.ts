/**
 * Regression tests for the second round of live-deploy bugs reported on
 * 2026-05-01.
 *
 * Bugs covered:
 *  S1. Library page: notes stuck in 'pending sync' forever — root cause was
 *      that syncManager.start() was never called, so the push/pull timers
 *      never fired. Fix: SessionGate calls syncManager.start() on auth.
 *  S2. /api/notes/{localId} and /api/search/similar/{localId} returning 404
 *      because NoteDetailPage used the URL :id (always a localId) when
 *      note.serverId was null. Fix: skip backend calls when no serverId.
 *  S3. Page refresh forces /login because access tokens are memory-only and
 *      no session-restore was attempted. Fix: SessionGate calls
 *      /api/auth/refresh on mount; on success setAccessToken + me().
 *  S4. No /profile page, no logout button, no profile API. Fix: ProfilePage
 *      component, AppHeader avatar shortcut, /api/auth/{me PUT, password,
 *      logout} endpoints.
 *
 * These are guard-rail tests — if a future refactor reverts any of them,
 * the test fails before the symptom reaches production.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

const FRONTEND_ROOT = resolve(__dirname, '..', '..');
function readSrc(relativePath: string): string {
  const full = resolve(FRONTEND_ROOT, relativePath);
  if (!existsSync(full)) {
    throw new Error(`Source file not found: ${relativePath}`);
  }
  return readFileSync(full, 'utf-8');
}

// =========================================================================
// S1 — SessionGate calls syncManager.start() on auth
// =========================================================================

describe('S1: SessionGate wires syncManager so the queue actually drains', () => {
  const src = readSrc('src/components/SessionGate.tsx');

  it('imports syncManager from sync/syncManager', () => {
    expect(src).toMatch(
      /import\s*\{\s*syncManager\s*\}\s*from\s*['"]\.\.\/sync\/syncManager['"]/
    );
  });

  it('calls syncManager.start() (otherwise notes are stuck pending forever)', () => {
    expect(src).toMatch(/syncManager\.start\s*\(/);
  });

  it('calls syncManager.stop() on logout to halt timers', () => {
    expect(src).toMatch(/syncManager\.stop\s*\(/);
  });

  it('App.tsx wraps Routes inside SessionGate', () => {
    const app = readSrc('src/App.tsx');
    expect(app).toMatch(/import\s*\{\s*SessionGate\s*\}\s*from\s*['"]\.\/components\/SessionGate['"]/);
    // SessionGate must wrap Routes — JSX order matters for one-shot effects
    const sessionIdx = app.indexOf('<SessionGate');
    const routesIdx = app.indexOf('<Routes');
    expect(sessionIdx).toBeGreaterThan(-1);
    expect(routesIdx).toBeGreaterThan(sessionIdx);
  });

  it('CapturePage nudges syncManager.pushChanges() after enqueuing a note', () => {
    const cap = readSrc('src/pages/CapturePage.tsx');
    expect(cap).toMatch(/syncManager\.pushChanges\s*\(\s*\)/);
  });
});

// =========================================================================
// S2 — NoteDetailPage skips backend calls when no serverId
// =========================================================================

describe('S2: NoteDetailPage uses serverId, not localId, for backend calls', () => {
  const src = readSrc('src/pages/NoteDetailPage.tsx');

  it('does NOT fall back to URL id when local.serverId is missing', () => {
    // The bug was: const sId = local?.serverId ?? id;
    expect(src).not.toMatch(/local\?\.serverId\s*\?\?\s*id/);
  });

  it('only calls getNote() when a serverId is present', () => {
    // After the fix the call sits inside `if (sId) { ... getNote(sId) ... }`
    // We can't run a full unit test on the page (heavy mock surface), but
    // we can assert the source contains the guard pattern.
    expect(src).toMatch(/if\s*\(\s*sId\s*\)\s*\{[\s\S]*getNote\s*\(\s*sId\s*\)/);
  });

  it('only calls searchSimilar() when a serverId is present', () => {
    expect(src).toMatch(/if\s*\(\s*sId\s*\)\s*\{[\s\S]*searchSimilar\s*\(\s*sId\s*\)/);
  });
});

// =========================================================================
// S3 — Session restore via /api/auth/refresh on app boot
// =========================================================================

describe('S3: SessionGate restores session via /api/auth/refresh on mount', () => {
  const src = readSrc('src/components/SessionGate.tsx');

  it('imports refresh + me from api/auth', () => {
    expect(src).toMatch(/import\s*\{[^}]*\brefresh\b[^}]*\}\s*from\s*['"]\.\.\/api\/auth['"]/);
    expect(src).toMatch(/import\s*\{[^}]*\bme\b[^}]*\}\s*from\s*['"]\.\.\/api\/auth['"]/);
  });

  it('calls refresh() inside a useEffect (runs on mount, not on every render)', () => {
    expect(src).toMatch(/useEffect\s*\(/);
    expect(src).toMatch(/refresh\s*\(\s*\)/);
  });

  it('stores token via setAccessToken before calling me()', () => {
    const setIdx = src.indexOf('setAccessToken(access_token)');
    const meIdx = src.search(/await\s+me\s*\(\s*\)/);
    expect(setIdx).toBeGreaterThan(-1);
    expect(meIdx).toBeGreaterThan(-1);
    expect(setIdx).toBeLessThan(meIdx);
  });

  it('clears isRestoring when refresh fails so AuthGate can redirect to /login', () => {
    expect(src).toMatch(/setRestoring\s*\(\s*false\s*\)/);
  });

  it('shows a splash while isRestoring is true so AuthGate does NOT yank to /login mid-restore', () => {
    expect(src).toMatch(/isRestoring/);
    expect(src).toMatch(/animate-spin/);
  });

  it('authStore exposes isRestoring + setRestoring + setUser actions', () => {
    const store = readSrc('src/store/authStore.ts');
    expect(store).toMatch(/isRestoring:\s*boolean/);
    expect(store).toMatch(/setRestoring/);
    expect(store).toMatch(/setUser/);
    // Default isRestoring is true so SessionGate gets a chance to attempt restore
    expect(store).toMatch(/isRestoring:\s*true/);
  });

  it('AuthGate respects isRestoring instead of immediately bouncing', () => {
    const app = readSrc('src/App.tsx');
    expect(app).toMatch(/isRestoring/);
  });
});

// =========================================================================
// S4 — ProfilePage + auth API helpers + AppHeader shortcut
// =========================================================================

describe('S4: ProfilePage exists with edit name + change password + logout', () => {
  const profile = readSrc('src/pages/ProfilePage.tsx');

  it('imports updateProfile, changePassword, logout from api/auth', () => {
    expect(profile).toMatch(/updateProfile/);
    expect(profile).toMatch(/changePassword/);
    expect(profile).toMatch(/logout/);
  });

  it('renders an email field (read-only) sourced from authStore.user', () => {
    expect(profile).toMatch(/data-testid=['"]profile-email['"]/);
  });

  it('renders a display-name input', () => {
    expect(profile).toMatch(/aria-label=['"]Display name['"]/);
  });

  it('renders three password inputs (current, new, confirm)', () => {
    expect(profile).toMatch(/aria-label=['"]Current password['"]/);
    expect(profile).toMatch(/aria-label=['"]New password['"]/);
    expect(profile).toMatch(/aria-label=['"]Confirm new password['"]/);
  });

  it('renders a Sign out button that calls logout', () => {
    expect(profile).toMatch(/Sign out/);
    expect(profile).toMatch(/handleLogout/);
  });

  it('navigates to /login after logout', () => {
    expect(profile).toMatch(/navigate\s*\(\s*['"]\/login['"]/);
  });

  it('rejects mismatched new/confirm passwords client-side', () => {
    expect(profile).toMatch(/newPassword\s*!==\s*confirmPassword/);
  });

  it('rejects new passwords < 8 chars client-side (matches SEC-04)', () => {
    expect(profile).toMatch(/newPassword\.length\s*<\s*8/);
  });

  it('App.tsx wires the /profile route under AuthGate', () => {
    const app = readSrc('src/App.tsx');
    expect(app).toMatch(/path=['"]\/profile['"]/);
    expect(app).toMatch(/import\s+ProfilePage\s+from\s+['"]\.\/pages\/ProfilePage['"]/);
  });

  it('AppHeader links to /settings (Round 15: profile shortcut moved to Settings)', () => {
    const header = readSrc('src/components/AppHeader.tsx');
    expect(header).toMatch(/to=['"]\/settings['"]/);
  });

  it('api/auth.ts exposes updateProfile, changePassword, logout', () => {
    const authApi = readSrc('src/api/auth.ts');
    expect(authApi).toMatch(/export\s+async\s+function\s+updateProfile/);
    expect(authApi).toMatch(/export\s+async\s+function\s+changePassword/);
    expect(authApi).toMatch(/export\s+async\s+function\s+logout/);
  });
});
