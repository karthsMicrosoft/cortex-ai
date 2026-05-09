/**
 * RouteLoading.test.tsx — TDD red phase
 *
 * Tests for `frontend/src/components/RouteLoading.tsx` — the Suspense fallback
 * spinner used while lazy-loaded route chunks are downloading.
 *
 * Requirements:
 *   - Exposes role="status" so screen-readers announce it as a live region
 *   - Has aria-label "Loading page" by default
 *   - Renders the default visible label "Loading..."
 *   - Accepts an optional `label` prop that overrides the visible text
 *   - Centered full-screen container styled to the dark slate theme
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

import { RouteLoading } from '../components/RouteLoading';

describe('RouteLoading', () => {
  it('renders with role="status" for accessibility', () => {
    render(<RouteLoading />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('has aria-label "Loading page" by default', () => {
    render(<RouteLoading />);
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'Loading page');
  });

  it('shows the default visible "Loading..." label', () => {
    render(<RouteLoading />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('renders a custom label when provided', () => {
    render(<RouteLoading label="Loading insights…" />);
    expect(screen.getByText('Loading insights…')).toBeInTheDocument();
  });

  it('uses the dark slate full-screen container', () => {
    render(<RouteLoading />);
    const status = screen.getByRole('status');
    // Container should use min-h-screen + the slate background used elsewhere.
    expect(status.className).toMatch(/min-h-screen/);
    expect(status.className).toMatch(/0F172A|bg-slate/);
  });
});
