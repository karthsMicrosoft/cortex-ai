/**
 * Task 5 / 3.1 — BottomNav — TDD red
 *
 * Tests that `frontend/src/components/BottomNav.tsx`:
 *   - Fixed bottom bar with four tabs: Capture, Library, Insights, Create
 *   - Uses lucide icons (or some icon)
 *   - Uses react-router-dom NavLink for each tab
 *   - Active tab has visual indicator (active class or aria-current)
 *   - Visible on every page (rendered inside protected layout)
 */

import { describe, it, expect, vi, beforeEach, afterEach, afterAll } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Import component under test
// ---------------------------------------------------------------------------

import { BottomNav } from '../components/BottomNav';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderBottomNav(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="*" element={<BottomNav />} />
      </Routes>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('BottomNav (Task 5 / 3.1)', () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  // --- Renders ---

  it('renders the bottom navigation', () => {
    renderBottomNav();
    const nav = screen.getByRole('navigation');
    expect(nav).toBeInTheDocument();
  });

  it('nav is fixed to bottom (has fixed class or position style)', () => {
    renderBottomNav();
    const nav = screen.getByRole('navigation');
    expect(nav.className).toMatch(/fixed|bottom/i);
  });

  // --- Six visible tabs by default (Tasks enabled; Canvas hidden behind VITE_FEATURE_CANVAS) ---

  it('renders exactly six nav tab links by default (Tasks visible, Canvas hidden)', () => {
    renderBottomNav();
    const links = screen.getAllByRole('link');
    expect(links.length).toBe(6);
  });

  it('does NOT render a Canvas tab by default', () => {
    renderBottomNav();
    expect(screen.queryByRole('link', { name: /^canvas$/i })).toBeNull();
  });

  it('has a Capture tab', () => {
    renderBottomNav();
    expect(screen.getByRole('link', { name: /capture/i })).toBeInTheDocument();
  });

  it('has a Library tab', () => {
    renderBottomNav();
    expect(screen.getByRole('link', { name: /library/i })).toBeInTheDocument();
  });

  it('has a Tasks tab', () => {
    renderBottomNav();
    expect(screen.getByRole('link', { name: /^tasks$/i })).toBeInTheDocument();
  });

  it('has an Insights tab', () => {
    renderBottomNav();
    expect(screen.getByRole('link', { name: /insights/i })).toBeInTheDocument();
  });

  it('has a Create tab', () => {
    renderBottomNav();
    expect(screen.getByRole('link', { name: /create/i })).toBeInTheDocument();
  });

  it('has an Ask tab (PR 4.2)', () => {
    renderBottomNav();
    expect(screen.getByRole('link', { name: /^ask$/i })).toBeInTheDocument();
  });

  it('Ask tab links to /ask (PR 4.2)', () => {
    renderBottomNav();
    const link = screen.getByRole('link', { name: /^ask$/i });
    expect(link.getAttribute('href')).toBe('/ask');
  });

  it('Ask tab is active when at /ask (PR 4.2)', () => {
    renderBottomNav('/ask');
    const link = screen.getByRole('link', { name: /^ask$/i });
    const isActive =
      link.getAttribute('aria-current') === 'page' || link.className.includes('active');
    expect(isActive).toBe(true);
  });

  it('Ask tab renders an icon (PR 4.2)', () => {
    renderBottomNav();
    const link = screen.getByRole('link', { name: /^ask$/i });
    expect(link.querySelector('svg')).not.toBeNull();
  });

  // --- Route links ---

  it('Capture tab links to / (root)', () => {
    renderBottomNav();
    const link = screen.getByRole('link', { name: /capture/i });
    expect(link.getAttribute('href')).toBe('/');
  });

  it('Library tab links to /library', () => {
    renderBottomNav();
    const link = screen.getByRole('link', { name: /library/i });
    expect(link.getAttribute('href')).toBe('/library');
  });

  it('Tasks tab links to /tasks', () => {
    renderBottomNav();
    const link = screen.getByRole('link', { name: /^tasks$/i });
    expect(link.getAttribute('href')).toBe('/tasks');
  });

  it('Insights tab links to /insights', () => {
    renderBottomNav();
    const link = screen.getByRole('link', { name: /insights/i });
    expect(link.getAttribute('href')).toBe('/insights');
  });

  it('Create tab links to /create', () => {
    renderBottomNav();
    const link = screen.getByRole('link', { name: /create/i });
    expect(link.getAttribute('href')).toBe('/create');
  });

  // --- Active state ---

  it('Capture tab is active when at /', () => {
    renderBottomNav('/');
    const link = screen.getByRole('link', { name: /capture/i });
    // Either aria-current="page" or an "active" class
    const isActive =
      link.getAttribute('aria-current') === 'page' || link.className.includes('active');
    expect(isActive).toBe(true);
  });

  it('Library tab is active when at /library', () => {
    renderBottomNav('/library');
    const link = screen.getByRole('link', { name: /library/i });
    const isActive =
      link.getAttribute('aria-current') === 'page' || link.className.includes('active');
    expect(isActive).toBe(true);
  });

  it('Tasks tab is active when at /tasks', () => {
    renderBottomNav('/tasks');
    const link = screen.getByRole('link', { name: /^tasks$/i });
    const isActive =
      link.getAttribute('aria-current') === 'page' || link.className.includes('active');
    expect(isActive).toBe(true);
  });

  it('Insights tab is active when at /insights', () => {
    renderBottomNav('/insights');
    const link = screen.getByRole('link', { name: /insights/i });
    const isActive =
      link.getAttribute('aria-current') === 'page' || link.className.includes('active');
    expect(isActive).toBe(true);
  });

  it('Create tab is active when at /create', () => {
    renderBottomNav('/create');
    const link = screen.getByRole('link', { name: /create/i });
    const isActive =
      link.getAttribute('aria-current') === 'page' || link.className.includes('active');
    expect(isActive).toBe(true);
  });

  // --- Icons ---

  it('each tab has an icon (svg or img)', () => {
    renderBottomNav();
    const nav = screen.getByRole('navigation');
    // Lucide icons render as SVG elements
    const icons = nav.querySelectorAll('svg');
    expect(icons.length).toBeGreaterThanOrEqual(6);
  });

  // --- Accessibility ---

  it('all tabs have accessible text (aria-label or visible text)', () => {
    renderBottomNav();
    const links = screen.getAllByRole('link');
    links.forEach((link) => {
      const hasText = link.textContent && link.textContent.trim().length > 0;
      const hasAriaLabel = link.getAttribute('aria-label');
      expect(hasText || hasAriaLabel).toBeTruthy();
    });
  });

  // --- Bottom styling ---

  it('nav has w-full class (full width)', () => {
    renderBottomNav();
    const nav = screen.getByRole('navigation');
    expect(nav.className).toMatch(/w-full/);
  });

  it('nav has bottom-0 positioning class', () => {
    renderBottomNav();
    const nav = screen.getByRole('navigation');
    expect(nav.className).toMatch(/bottom-0/);
  });
});

// ---------------------------------------------------------------------------
// Round 28 — Canvas feature flag (VITE_FEATURE_CANVAS)
// ---------------------------------------------------------------------------

describe('BottomNav — Canvas feature flag (Round 28)', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  afterAll(() => {
    vi.unstubAllEnvs();
  });

  it('renders the Canvas tab when VITE_FEATURE_CANVAS=true', () => {
    vi.stubEnv('VITE_FEATURE_CANVAS', 'true');
    renderBottomNav();
    expect(screen.getByRole('link', { name: /^canvas$/i })).toBeInTheDocument();
    expect(screen.getAllByRole('link').length).toBe(7);
  });

  it('hides the Canvas tab when VITE_FEATURE_CANVAS is unset', () => {
    vi.stubEnv('VITE_FEATURE_CANVAS', '');
    renderBottomNav();
    expect(screen.queryByRole('link', { name: /^canvas$/i })).toBeNull();
    expect(screen.getAllByRole('link').length).toBe(6);
  });

  it('hides the Canvas tab when VITE_FEATURE_CANVAS=false', () => {
    vi.stubEnv('VITE_FEATURE_CANVAS', 'false');
    renderBottomNav();
    expect(screen.queryByRole('link', { name: /^canvas$/i })).toBeNull();
    expect(screen.getAllByRole('link').length).toBe(6);
  });
});

// ---------------------------------------------------------------------------
// Round 35 — Tasks feature flag (VITE_FEATURE_TASKS)
// ---------------------------------------------------------------------------

describe('BottomNav — Tasks feature flag (Round 35)', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('renders the Tasks tab by default', () => {
    renderBottomNav();
    expect(screen.getByRole('link', { name: /^tasks$/i })).toBeInTheDocument();
  });

  it('renders the Tasks tab when VITE_FEATURE_TASKS=true', () => {
    vi.stubEnv('VITE_FEATURE_TASKS', 'true');
    renderBottomNav();
    expect(screen.getByRole('link', { name: /^tasks$/i })).toBeInTheDocument();
  });

  it('hides the Tasks tab when VITE_FEATURE_TASKS=false', () => {
    vi.stubEnv('VITE_FEATURE_TASKS', 'false');
    renderBottomNav();
    expect(screen.queryByRole('link', { name: /^tasks$/i })).toBeNull();
  });

  it('hides the Tasks tab when VITE_FEATURE_TASKS=0', () => {
    vi.stubEnv('VITE_FEATURE_TASKS', '0');
    renderBottomNav();
    expect(screen.queryByRole('link', { name: /^tasks$/i })).toBeNull();
  });
});
