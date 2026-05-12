/**
 * WikiContent.test.tsx — PR 6.5
 *
 * Tests for `<WikiContent />`:
 *  - plain text passthrough when no [[refs]]
 *  - resolved [[Title]] becomes <a href="/note/<id>">
 *  - unresolved [[Unknown]] renders as plain text + tooltip
 *  - multiple refs all rendered correctly
 *  - case-insensitive resolution via the wikiLinks map
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import React from 'react';

import { WikiContent } from '../components/WikiContent';

function renderWith(content: string, links: Map<string, { id: string; title: string }>) {
  return render(
    <MemoryRouter>
      <WikiContent content={content} wikiLinks={links} />
    </MemoryRouter>,
  );
}

describe('WikiContent (PR 6.5)', () => {
  it('renders plain text when no wiki refs', () => {
    renderWith('hello world, no refs here', new Map());
    expect(screen.getByText(/hello world, no refs here/i)).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('[[Title]] becomes a clickable link when resolved', () => {
    const links = new Map<string, { id: string; title: string }>([
      ['foo', { id: 'note-1', title: 'Foo' }],
    ]);
    renderWith('see [[Foo]] now', links);
    const link = screen.getByRole('link', { name: /foo/i });
    expect(link).toHaveAttribute('href', '/note/note-1');
  });

  it('[[Unknown]] renders as plain text with tooltip when unresolved', () => {
    renderWith('orphan [[Unknown]] ref', new Map());
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    const orphan = screen.getByText(/\[\[Unknown\]\]/);
    expect(orphan).toBeInTheDocument();
    expect(orphan).toHaveAttribute('title', expect.stringMatching(/no matching note/i));
  });

  it('multiple refs all rendered correctly', () => {
    const links = new Map<string, { id: string; title: string }>([
      ['alpha', { id: 'a', title: 'Alpha' }],
      ['beta', { id: 'b', title: 'Beta' }],
    ]);
    renderWith('refs: [[Alpha]] then [[Beta]] and [[Gamma]] done', links);
    const alphaLink = screen.getByRole('link', { name: /alpha/i });
    const betaLink = screen.getByRole('link', { name: /beta/i });
    expect(alphaLink).toHaveAttribute('href', '/note/a');
    expect(betaLink).toHaveAttribute('href', '/note/b');
    // Gamma unresolved
    expect(screen.getByText(/\[\[Gamma\]\]/)).toBeInTheDocument();
  });

  it('case-insensitive resolution via the wikiLinks map', () => {
    // Map keys are lowercased; the ref text in content uses uppercase.
    const links = new Map<string, { id: string; title: string }>([
      ['foo', { id: 'note-1', title: 'Foo' }],
    ]);
    renderWith('uppercase [[FOO]]', links);
    const link = screen.getByRole('link', { name: /foo/i });
    expect(link).toHaveAttribute('href', '/note/note-1');
  });
});
