import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DeadlinePill } from '../components/DeadlinePill';

describe('DeadlinePill', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-05T10:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders preview text for today and tomorrow', () => {
    const { rerender } = render(<DeadlinePill mode="preview" dueAt="2026-06-05T18:00:00Z" />);
    expect(screen.getByText(/Today/i)).toBeInTheDocument();

    rerender(<DeadlinePill mode="preview" dueAt="2026-06-06T23:59:00Z" priority={1} recurring="weekly" />);
    expect(screen.getByText(/Tomorrow/i)).toBeInTheDocument();
    expect(screen.getByText(/High/i)).toBeInTheDocument();
    expect(screen.getByText(/Weekly/i)).toBeInTheDocument();
  });

  it('renders far future, priority-only, and recurring-only previews', () => {
    const { rerender } = render(<DeadlinePill mode="preview" dueAt="2026-07-15T23:59:00Z" />);
    expect(screen.getByText(/Jul\s+15/i)).toBeInTheDocument();

    rerender(<DeadlinePill mode="preview" priority={1} />);
    expect(screen.getByText('High')).toBeInTheDocument();

    rerender(<DeadlinePill mode="preview" recurring="monthly" />);
    expect(screen.getByText('Monthly')).toBeInTheDocument();
  });

  it('renders nothing when all fields are null', () => {
    render(<DeadlinePill mode="preview" dueAt={null} priority={null} recurring={null} />);
    expect(screen.queryByTestId('deadline-pill-preview')).toBeNull();
  });

  it('opens the editor and saves due_at changes', async () => {
    const onUpdate = vi.fn().mockResolvedValue(undefined);
    const { container } = render(
      <DeadlinePill mode="editable" dueAt="2026-06-06T23:59:00Z" onUpdate={onUpdate} />,
    );

    fireEvent.click(screen.getByTestId('deadline-pill-editable'));
    expect(screen.getByTestId('deadline-pill-editable-editor')).toBeInTheDocument();

    const input = container.querySelector('input[type="datetime-local"]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '2026-06-06T15:30' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
      await Promise.resolve();
    });

    expect(onUpdate).toHaveBeenCalledWith({
      due_at: new Date('2026-06-06T15:30').toISOString(),
      priority: null,
      recurring: null,
    });
  });

  it('marks done with an ISO timestamp', async () => {
    const onUpdate = vi.fn().mockResolvedValue(undefined);
    render(<DeadlinePill mode="editable" priority={1} onUpdate={onUpdate} />);

    fireEvent.click(screen.getByTestId('deadline-pill-editable'));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /mark done/i }));
      await Promise.resolve();
    });

    expect(onUpdate).toHaveBeenCalledWith({ done_at: '2026-06-05T10:00:00.000Z' });
  });

  it('clears deadline fields', async () => {
    const onUpdate = vi.fn().mockResolvedValue(undefined);
    render(<DeadlinePill mode="editable" dueAt="2026-06-06T23:59:00Z" priority={1} recurring="daily" onUpdate={onUpdate} />);

    fireEvent.click(screen.getByTestId('deadline-pill-editable'));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /clear/i }));
      await Promise.resolve();
    });

    expect(onUpdate).toHaveBeenCalledWith({ due_at: null, priority: null, recurring: null });
  });
});
