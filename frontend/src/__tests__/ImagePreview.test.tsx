/**
 * ImagePreview component — Round 15 / PR #24
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { ImagePreview } from '../components/ImagePreview';

describe('ImagePreview', () => {
  it('renders an image with the provided src', () => {
    render(<ImagePreview src="blob:fake" alt="my photo" />);
    const img = screen.getByAltText('my photo') as HTMLImageElement;
    expect(img).toBeInTheDocument();
    expect(img.src).toContain('blob:fake');
  });

  it('uses a default alt when none is provided', () => {
    render(<ImagePreview src="blob:fake" />);
    const img = screen.getByRole('img');
    expect(img).toBeInTheDocument();
  });

  it('renders a remove button when onRemove is provided', () => {
    const onRemove = vi.fn();
    render(<ImagePreview src="blob:fake" onRemove={onRemove} />);
    const btn = screen.getByRole('button', { name: /remove|clear|cancel|×/i });
    expect(btn).toBeInTheDocument();
  });

  it('does NOT render a remove button when onRemove is missing', () => {
    render(<ImagePreview src="blob:fake" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('clicking remove invokes onRemove', () => {
    const onRemove = vi.fn();
    render(<ImagePreview src="blob:fake" onRemove={onRemove} />);
    fireEvent.click(screen.getByRole('button', { name: /remove|clear|cancel|×/i }));
    expect(onRemove).toHaveBeenCalledTimes(1);
  });
});
