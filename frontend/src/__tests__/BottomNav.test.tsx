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

import { describe, it, expect, vi, beforeEach } from 'vitest';
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
    vi.clearAllMocks();
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

  // --- Four tabs ---

  it('renders exactly four nav tab links', () => {
    renderBottomNav();
    const links = screen.getAllByRole('link');
    expect(links.length).toBe(4);
  });

  it('has a Capture tab', () => {
    renderBottomNav();
    expect(screen.getByRole('link', { name: /capture/i })).toBeInTheDocument();
  });

  it('has a Library tab', () => {
    renderBottomNav();
    expect(screen.getByRole('link', { name: /library/i })).toBeInTheDocument();
  });

  it('has an Insights tab', () => {
    renderBottomNav();
    expect(screen.getByRole('link', { name: /insights/i })).toBeInTheDocument();
  });

  it('has a Create tab', () => {
    renderBottomNav();
    expect(screen.getByRole('link', { name: /create/i })).toBeInTheDocument();
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
    expect(icons.length).toBeGreaterThanOrEqual(4);
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
