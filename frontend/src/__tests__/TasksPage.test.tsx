import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import type { Task, TaskListResponse } from '../services/api/tasks';

const { mockListTasks, mockToggleDone, mockUpdateNote, mockNavigate } = vi.hoisted(() => ({
  mockListTasks: vi.fn(),
  mockToggleDone: vi.fn(),
  mockUpdateNote: vi.fn(),
  mockNavigate: vi.fn(),
}));

vi.mock('../services/api/tasks', () => ({
  listTasks: mockListTasks,
  toggleDone: mockToggleDone,
  updateNote: mockUpdateNote,
}));

vi.mock('../components/DeadlinePill', () => ({
  DeadlinePill: ({
    testId,
    onUpdate,
  }: {
    testId?: string;
    onUpdate?: (changes: { due_at?: string | null; priority?: 1 | 2 | 3 | null; recurring?: 'daily' | 'weekly' | 'monthly' | null }) => Promise<void>;
  }) => (
    <button
      type="button"
      data-testid={testId ?? 'deadline-pill-editable'}
      onClick={() => void onUpdate?.({ due_at: '2026-06-06T18:00:00.000Z', priority: 2, recurring: 'weekly' })}
    >
      Edit deadline
    </button>
  ),
}));

vi.mock('react-router-dom', async (importActual) => {
  const actual = await importActual<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

import TasksPage from '../pages/TasksPage';

const TASK: Task = {
  id: 'task-1',
  title: 'Buy milk',
  content: 'Buy milk and bread on the way home',
  due_at: '2026-06-06T18:00:00.000Z',
  priority: 1,
  recurring: null,
  done_at: null,
  category: 'Home',
  created_at: '2026-06-01T12:00:00.000Z',
  updated_at: '2026-06-01T12:00:00.000Z',
};

function renderTasksPage() {
  return render(
    <MemoryRouter>
      <TasksPage />
    </MemoryRouter>,
  );
}

describe('TasksPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListTasks.mockResolvedValue({ items: [TASK], total: 1 });
    mockToggleDone.mockResolvedValue(undefined);
    mockUpdateNote.mockResolvedValue(undefined);
  });

  it('renders loading state initially', async () => {
    let resolveList!: (value: TaskListResponse) => void;
    mockListTasks.mockReturnValueOnce(new Promise((resolve) => {
      resolveList = resolve;
    }));

    renderTasksPage();

    expect(screen.getByRole('status', { name: /loading tasks/i })).toBeInTheDocument();
    resolveList({ items: [], total: 0 });
    await screen.findByText('No open tasks — nice work.');
  });

  it('renders task list after fetch resolves', async () => {
    renderTasksPage();

    expect(await screen.findByText('Buy milk')).toBeInTheDocument();
    expect(screen.getByText('Home')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /mark done/i })).toBeInTheDocument();
    expect(screen.getByTestId('deadline-pill-task-1')).toBeInTheDocument();
  });

  it('shows the empty state when there are no tasks', async () => {
    mockListTasks.mockResolvedValue({ items: [], total: 0 });

    renderTasksPage();

    expect(await screen.findByText('No open tasks — nice work.')).toBeInTheDocument();
  });

  it('re-fetches with the new status when switching tabs', async () => {
    mockListTasks.mockResolvedValue({ items: [], total: 0 });
    renderTasksPage();

    await waitFor(() => {
      expect(mockListTasks).toHaveBeenCalledWith(expect.objectContaining({ status: 'open', limit: 50, offset: 0 }));
    });

    fireEvent.click(screen.getByRole('tab', { name: /overdue/i }));

    await waitFor(() => {
      expect(mockListTasks).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'overdue', limit: 50, offset: 0 }));
    });
  });

  it('calls toggleDone then refreshes when Mark done is clicked', async () => {
    renderTasksPage();
    await screen.findByText('Buy milk');
    mockListTasks.mockClear();

    fireEvent.click(screen.getByRole('button', { name: /mark done/i }));

    await waitFor(() => expect(mockToggleDone).toHaveBeenCalledWith('task-1'));
    await waitFor(() => {
      expect(mockListTasks).toHaveBeenCalledWith(expect.objectContaining({ status: 'open', limit: 50, offset: 0 }));
    });
  });

  it('calls updateNote then refreshes when the deadline pill updates', async () => {
    renderTasksPage();
    await screen.findByText('Buy milk');
    mockListTasks.mockClear();

    fireEvent.click(screen.getByTestId('deadline-pill-task-1'));

    await waitFor(() => {
      expect(mockUpdateNote).toHaveBeenCalledWith('task-1', {
        due_at: '2026-06-06T18:00:00.000Z',
        priority: 2,
        recurring: 'weekly',
      });
    });
    await waitFor(() => {
      expect(mockListTasks).toHaveBeenCalledWith(expect.objectContaining({ status: 'open', limit: 50, offset: 0 }));
    });
  });

  it('navigates to the note detail route when a task title is tapped', async () => {
    renderTasksPage();

    fireEvent.click(await screen.findByRole('button', { name: /buy milk/i }));

    expect(mockNavigate).toHaveBeenCalledWith('/notes/task-1');
  });
});
