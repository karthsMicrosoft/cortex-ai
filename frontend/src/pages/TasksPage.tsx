import { useCallback, useEffect, useState } from 'react';
import type { ComponentProps } from 'react';
import { CheckSquare } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { DeadlinePill } from '../components/DeadlinePill';
import {
  listTasks,
  toggleDone,
  updateNote,
  type Task,
  type TaskNoteUpdate,
  type TaskStatus,
} from '../services/api/tasks';

const PAGE_SIZE = 50;
const TABS: Array<{ label: string; status: TaskStatus }> = [
  { label: 'Open', status: 'open' },
  { label: 'Overdue', status: 'overdue' },
  { label: 'Done', status: 'done' },
];
const PRIORITIES: Array<{ label: string; value?: 1 | 2 | 3 }> = [
  { label: 'All' },
  { label: 'High', value: 1 },
  { label: 'Medium', value: 2 },
  { label: 'Low', value: 3 },
];

type DeadlineUpdate = Parameters<NonNullable<ComponentProps<typeof DeadlinePill>['onUpdate']>>[0];

function taskTitle(task: Task): string {
  const title = task.title?.trim();
  if (title) return title;

  const content = task.content.trim();
  if (content.length <= 40) return content || 'Untitled task';
  return `${content.slice(0, 40)}…`;
}

function emptyMessage(status: TaskStatus): string {
  if (status === 'open') return 'No open tasks — nice work.';
  if (status === 'overdue') return 'No overdue tasks.';
  return 'No done tasks yet.';
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : 'Unable to load tasks.';
}

function patchFromDeadlineUpdate(changes: DeadlineUpdate): TaskNoteUpdate {
  const patch: TaskNoteUpdate = {};
  if ('due_at' in changes) patch.due_at = changes.due_at ?? null;
  if ('priority' in changes) patch.priority = changes.priority ?? null;
  if ('recurring' in changes) patch.recurring = changes.recurring ?? null;
  return patch;
}

export default function TasksPage(): React.ReactElement {
  const navigate = useNavigate();
  const [status, setStatus] = useState<TaskStatus>('open');
  const [priority, setPriority] = useState<1 | 2 | 3 | undefined>(undefined);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchPage = useCallback(
    async (offset: number, mode: 'replace' | 'append' = 'replace') => {
      setError(null);
      if (mode === 'append') {
        setIsLoadingMore(true);
      } else {
        setIsLoading(true);
        setTasks([]);
      }

      try {
        const response = await listTasks({
          status,
          limit: PAGE_SIZE,
          offset,
          ...(priority ? { priority } : {}),
        });
        setTotal(response.total);
        setTasks((prev) => (mode === 'append' ? [...prev, ...response.items] : response.items));
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setIsLoading(false);
        setIsLoadingMore(false);
      }
    },
    [priority, status],
  );

  useEffect(() => {
    void fetchPage(0, 'replace');
  }, [fetchPage]);

  const refresh = useCallback(async () => {
    await fetchPage(0, 'replace');
  }, [fetchPage]);

  const handleToggleDone = useCallback(
    async (taskId: string) => {
      setBusyTaskId(taskId);
      setError(null);
      try {
        await toggleDone(taskId);
        await refresh();
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setBusyTaskId(null);
      }
    },
    [refresh],
  );

  const handleDeadlineUpdate = useCallback(
    async (taskId: string, changes: DeadlineUpdate) => {
      setBusyTaskId(taskId);
      setError(null);
      try {
        const patch = patchFromDeadlineUpdate(changes);
        if (Object.keys(patch).length > 0) {
          await updateNote(taskId, patch);
        } else if ('done_at' in changes) {
          await toggleDone(taskId);
        }
        await refresh();
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setBusyTaskId(null);
      }
    },
    [refresh],
  );

  const hasMore = tasks.length < total;

  return (
    <div className="flex min-h-screen flex-col bg-[#0F172A] pb-24 text-slate-100">
      <header className="border-b border-slate-700 px-4 py-4">
        <div className="flex items-center gap-2">
          <CheckSquare className="h-5 w-5 text-indigo-300" aria-hidden="true" />
          <div>
            <h1 className="text-lg font-semibold">Tasks</h1>
            <p className="text-xs text-slate-400">Reminders and follow-ups from your notes</p>
          </div>
        </div>
      </header>

      <section className="border-b border-slate-700/50 px-4 py-3">
        <div role="tablist" aria-label="Task status" className="mb-3 grid grid-cols-3 gap-2 rounded-2xl bg-slate-900/70 p-1">
          {TABS.map((tab) => {
            const isActive = status === tab.status;
            return (
              <button
                key={tab.status}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setStatus(tab.status)}
                className={[
                  'rounded-xl px-3 py-2 text-sm font-semibold transition-colors',
                  isActive
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200',
                ].join(' ')}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="flex gap-2 overflow-x-auto pb-1" aria-label="Priority filter">
          {PRIORITIES.map((item) => {
            const isActive = priority === item.value || (item.value === undefined && priority === undefined);
            return (
              <button
                key={item.label}
                type="button"
                onClick={() => setPriority(item.value)}
                className={[
                  'shrink-0 rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                  isActive
                    ? 'border-indigo-500 bg-indigo-900/50 text-indigo-200'
                    : 'border-slate-600 bg-slate-800 text-slate-400 hover:border-slate-500',
                ].join(' ')}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      </section>

      <main className="flex flex-1 flex-col gap-3 px-4 py-4">
        {isLoading ? (
          <div role="status" aria-label="Loading tasks" className="flex flex-1 items-center justify-center text-sm text-slate-400">
            Loading tasks…
          </div>
        ) : error ? (
          <div role="alert" className="rounded-2xl border border-red-700/40 bg-red-950/40 p-4 text-sm text-red-200">
            <p>{error}</p>
            <button
              type="button"
              onClick={() => void refresh()}
              className="mt-3 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-500"
            >
              Retry
            </button>
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex flex-1 items-center justify-center rounded-2xl border border-slate-700 bg-slate-900/60 p-6 text-center">
            <p className="text-sm text-slate-400">{emptyMessage(status)}</p>
          </div>
        ) : (
          <>
            {tasks.map((task) => (
              <article
                key={task.id}
                className="rounded-2xl border border-slate-700 bg-slate-900/80 p-4 shadow-sm shadow-slate-950/20"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="mb-2">
                      <DeadlinePill
                        mode="editable"
                        dueAt={task.due_at}
                        priority={task.priority}
                        recurring={task.recurring}
                        doneAt={task.done_at}
                        testId={`deadline-pill-${task.id}`}
                        onUpdate={(changes) => handleDeadlineUpdate(task.id, changes)}
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => navigate(`/notes/${task.id}`)}
                      className="block max-w-full text-left text-base font-semibold text-slate-100 hover:text-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                    >
                      {taskTitle(task)}
                    </button>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      <span className="rounded-full border border-slate-700 bg-slate-950/60 px-2 py-0.5 text-slate-300">
                        {task.category}
                      </span>
                      {task.done_at ? <span>Done</span> : null}
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => void handleToggleDone(task.id)}
                    disabled={busyTaskId === task.id}
                    className="self-start rounded-lg border border-indigo-500/60 bg-indigo-950/50 px-3 py-1.5 text-xs font-semibold text-indigo-100 transition-colors hover:bg-indigo-900 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {busyTaskId === task.id ? 'Saving…' : task.done_at ? 'Mark open' : 'Mark done'}
                  </button>
                </div>
              </article>
            ))}

            {hasMore ? (
              <button
                type="button"
                onClick={() => void fetchPage(tasks.length, 'append')}
                disabled={isLoadingMore}
                className="mt-2 rounded-xl border border-slate-600 bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-200 hover:border-indigo-500 hover:text-indigo-100 disabled:opacity-60"
              >
                {isLoadingMore ? 'Loading…' : 'Load More'}
              </button>
            ) : null}
          </>
        )}
      </main>
    </div>
  );
}
