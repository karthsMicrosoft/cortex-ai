/**
 * Task 1 (Tailwind / bootstrap config) — TDD red
 *
 * Tests that tailwind.config.js:
 *   - exports `darkMode: 'class'`
 *   - content globs include ./index.html and ./src/**\/*.{ts,tsx}
 *   - theme extension includes indigo accent #4F46E5
 *
 * We read tailwind.config.js as text (static analysis) because
 * it uses CommonJS `module.exports` that doesn't tree-shake cleanly
 * in Vitest ESM mode.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'fs';
import { resolve } from 'path';

const TAILWIND_PATH = resolve(process.cwd(), 'tailwind.config.js');

let tailwindSource = '';
try {
  tailwindSource = readFileSync(TAILWIND_PATH, 'utf-8');
} catch {
  tailwindSource = '';
}

describe('tailwind.config.js (Task 1.3)', () => {
  it('file exists', () => {
    expect(existsSync(TAILWIND_PATH)).toBe(true);
  });

  it('darkMode is set to "class"', () => {
    expect(tailwindSource).toMatch(/darkMode\s*:\s*['"]class['"]/);
  });

  it('content includes ./index.html', () => {
    expect(tailwindSource).toMatch(/['"]\.\/index\.html['"]/);
  });

  it('content includes ./src/**/*.{ts,tsx} glob', () => {
    // Accept various quote styles and spacing
    expect(tailwindSource).toMatch(/src\/\*\*\/\*\.\{ts,tsx\}/);
  });

  it('theme extension includes indigo accent #4F46E5', () => {
    expect(tailwindSource).toContain('#4F46E5');
  });
});

// ---------------------------------------------------------------------------
// index.html — root html class="dark"
// ---------------------------------------------------------------------------

const INDEX_HTML_PATH = resolve(process.cwd(), 'index.html');
let indexHtml = '';
try {
  indexHtml = readFileSync(INDEX_HTML_PATH, 'utf-8');
} catch {
  indexHtml = '';
}

describe('index.html (Task 1.5)', () => {
  it('file exists', () => {
    expect(existsSync(INDEX_HTML_PATH)).toBe(true);
  });

  it('<html> element has class="dark"', () => {
    expect(indexHtml).toMatch(/<html[^>]*class="[^"]*dark[^"]*"/);
  });

  it('<html> element has lang="en"', () => {
    expect(indexHtml).toMatch(/<html[^>]*lang="en"/);
  });

  it('has viewport meta tag', () => {
    expect(indexHtml).toMatch(/meta[^>]*viewport/);
  });

  it('has theme-color meta set to #4F46E5', () => {
    expect(indexHtml).toMatch(/theme-color/);
    expect(indexHtml).toContain('#4F46E5');
  });

  it('has a #root div', () => {
    expect(indexHtml).toMatch(/id="root"/);
  });

  it('loads src/main.tsx as a module script', () => {
    expect(indexHtml).toMatch(/src\/main\.tsx/);
    expect(indexHtml).toMatch(/type="module"/);
  });
});

// ---------------------------------------------------------------------------
// tsconfig.json — TypeScript compiler options
// ---------------------------------------------------------------------------

const TSCONFIG_PATH = resolve(process.cwd(), 'tsconfig.json');
let tsconfig: Record<string, unknown> = {};
try {
  tsconfig = JSON.parse(readFileSync(TSCONFIG_PATH, 'utf-8'));
} catch {
  tsconfig = {};
}

describe('tsconfig.json (Task 1.2)', () => {
  it('file exists', () => {
    expect(existsSync(TSCONFIG_PATH)).toBe(true);
  });

  it('compilerOptions.strict is true', () => {
    const co = tsconfig.compilerOptions as Record<string, unknown>;
    expect(co?.strict).toBe(true);
  });

  it('compilerOptions.noImplicitAny is true', () => {
    const co = tsconfig.compilerOptions as Record<string, unknown>;
    // noImplicitAny can be implied by strict:true; explicit is also acceptable
    expect(co?.strict === true || co?.noImplicitAny === true).toBe(true);
  });

  it('compilerOptions.target is ES2022', () => {
    const co = tsconfig.compilerOptions as Record<string, unknown>;
    expect(String(co?.target).toUpperCase()).toBe('ES2022');
  });

  it('compilerOptions.module is ESNext', () => {
    const co = tsconfig.compilerOptions as Record<string, unknown>;
    expect(String(co?.module).toUpperCase()).toBe('ESNEXT');
  });

  it('compilerOptions.jsx is react-jsx', () => {
    const co = tsconfig.compilerOptions as Record<string, unknown>;
    expect(co?.jsx).toBe('react-jsx');
  });

  it('compilerOptions.moduleResolution is bundler', () => {
    const co = tsconfig.compilerOptions as Record<string, unknown>;
    expect(String(co?.moduleResolution).toLowerCase()).toBe('bundler');
  });
});

// ---------------------------------------------------------------------------
// package.json — dependency pinning
// ---------------------------------------------------------------------------

const PACKAGE_JSON_PATH = resolve(process.cwd(), 'package.json');
let pkgJson: Record<string, unknown> = {};
try {
  pkgJson = JSON.parse(readFileSync(PACKAGE_JSON_PATH, 'utf-8'));
} catch {
  pkgJson = {};
}

describe('package.json — dependency pinning (Task 1.1)', () => {
  it('file exists', () => {
    expect(existsSync(PACKAGE_JSON_PATH)).toBe(true);
  });

  const deps = () => (pkgJson.dependencies as Record<string, string>) ?? {};
  const devDeps = () => (pkgJson.devDependencies as Record<string, string>) ?? {};

  it('react ^18.3.0 in dependencies', () => {
    expect(deps()['react']).toMatch(/\^18\./);
  });

  it('react-router-dom ^6 in dependencies', () => {
    expect(deps()['react-router-dom']).toMatch(/\^6\./);
  });

  it('zustand ^4 in dependencies', () => {
    expect(deps()['zustand']).toMatch(/\^4\./);
  });

  it('dexie ^4 in dependencies', () => {
    expect(deps()['dexie']).toMatch(/\^4\./);
  });

  it('vite ^5 in devDependencies', () => {
    expect(devDeps()['vite']).toMatch(/\^5\./);
  });

  it('vite-plugin-pwa ^0.20 in devDependencies', () => {
    expect(devDeps()['vite-plugin-pwa']).toMatch(/\^0\.20/);
  });

  it('vitest ^2 in devDependencies', () => {
    expect(devDeps()['vitest']).toMatch(/\^2\./);
  });

  it('@testing-library/react in devDependencies', () => {
    expect(devDeps()['@testing-library/react']).toBeTruthy();
  });

  it('@testing-library/jest-dom in devDependencies', () => {
    expect(devDeps()['@testing-library/jest-dom']).toBeTruthy();
  });

  it('jsdom in devDependencies', () => {
    expect(devDeps()['jsdom']).toBeTruthy();
  });

  it('tailwindcss ^3 in devDependencies', () => {
    expect(devDeps()['tailwindcss']).toMatch(/\^3\./);
  });

  it('typescript ^5 in devDependencies', () => {
    expect(devDeps()['typescript']).toMatch(/\^5\./);
  });
});
