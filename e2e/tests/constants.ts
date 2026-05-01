/**
 * constants.ts — shared non-test constants used by both auth.setup.ts and helpers.ts.
 *
 * Playwright forbids test files from importing other test files, so shared
 * credentials must live in a plain TypeScript module, not in auth.setup.ts.
 */
import * as path from 'path';

export const AUTH_FILE = path.join(__dirname, '..', '.auth', 'user.json');

// Fixed shared-user credentials. Auth.setup.ts handles the case where the
// user already exists (re-runs) by attempting login as a fallback.
export const SHARED_EMAIL = 'e2e-shared-cortex@example.com';
export const SHARED_PASSWORD = 'TestPass123*';
