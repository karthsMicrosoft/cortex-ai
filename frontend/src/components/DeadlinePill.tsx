import { useMemo, useRef, useState } from 'react';

export type DeadlinePriority = 1 | 2 | 3;
export type DeadlineRecurring = 'daily' | 'weekly' | 'monthly';

interface DeadlinePillProps {
  dueAt?: string | null;
  priority?: DeadlinePriority | null;
  recurring?: DeadlineRecurring | null;
  mode: 'preview' | 'editable';
  onUpdate?: (
    changes: Partial<{
      due_at: string | null;
      priority: DeadlinePriority | null;
      recurring: DeadlineRecurring | null;
      done_at: string | null;
    }>,
  ) => Promise<void>;
  doneAt?: string | null;
  testId?: string;
}

const priorityLabels: Record<DeadlinePriority, string> = {
  1: 'High',
  2: 'Medium',
  3: 'Low',
};

function titleCase(value: string): string {
  return `${value.charAt(0).toUpperCase()}${value.slice(1)}`;
}

function formatTime(date: Date): string {
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
    .format(date)
    .replace(/\s/g, '')
    .toLowerCase();
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function formatDueAt(value: string): string | null {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;

  const now = new Date();
  const dayDiff = Math.round(
    (startOfDay(date).getTime() - startOfDay(now).getTime()) / 86_400_000,
  );
  const time = formatTime(date);

  if (dayDiff === 0) return `📅 Today ${time}`;
  if (dayDiff === 1) return `📅 Tomorrow ${time}`;
  if (dayDiff === -1) return `📅 Yesterday ${time}`;

  if (Math.abs(dayDiff) < 7) {
    const weekday = new Intl.DateTimeFormat(undefined, { weekday: 'short' }).format(date);
    return `📅 ${weekday} ${time}`;
  }

  const includeYear = date.getFullYear() !== now.getFullYear();
  const formattedDate = new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    ...(includeYear ? { year: 'numeric' as const } : {}),
  }).format(date);
  return `📅 ${formattedDate}`;
}

function toDatetimeLocal(value?: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

export function DeadlinePill({
  dueAt,
  priority,
  recurring,
  mode,
  onUpdate,
  doneAt,
  testId,
}: DeadlinePillProps): React.ReactElement | null {
  const hasAnySignal = dueAt != null || priority != null || recurring != null;
  const [isOpen, setIsOpen] = useState(false);
  const [localDue, setLocalDue] = useState(() => toDatetimeLocal(dueAt));
  const [localPriority, setLocalPriority] = useState<DeadlinePriority | ''>(priority ?? '');
  const [localRecurring, setLocalRecurring] = useState<DeadlineRecurring | ''>(recurring ?? '');
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const chunks = useMemo(() => {
    const values: string[] = [];
    const due = dueAt ? formatDueAt(dueAt) : null;
    if (due) values.push(due);
    if (priority) values.push(priorityLabels[priority]);
    if (recurring) values.push(titleCase(recurring));
    return values;
  }, [dueAt, priority, recurring]);

  if (!hasAnySignal || chunks.length === 0) return null;

  const baseTestId = testId ?? (mode === 'preview' ? 'deadline-pill-preview' : 'deadline-pill-editable');

  const openEditor = (): void => {
    if (mode !== 'editable') return;
    setLocalDue(toDatetimeLocal(dueAt));
    setLocalPriority(priority ?? '');
    setLocalRecurring(recurring ?? '');
    setIsOpen(true);
  };

  const clearLongPress = (): void => {
    if (longPressTimer.current) clearTimeout(longPressTimer.current);
    longPressTimer.current = null;
  };

  const saveChanges = async (): Promise<void> => {
    await onUpdate?.({
      due_at: localDue ? new Date(localDue).toISOString() : null,
      priority: localPriority === '' ? null : localPriority,
      recurring: localRecurring === '' ? null : localRecurring,
    });
    setIsOpen(false);
  };

  const markDone = async (): Promise<void> => {
    await onUpdate?.({ done_at: doneAt ? null : new Date().toISOString() });
    setIsOpen(false);
  };

  const clearAll = async (): Promise<void> => {
    await onUpdate?.({ due_at: null, priority: null, recurring: null });
    setIsOpen(false);
  };

  const pillClasses = [
    'inline-flex max-w-full items-center gap-1 rounded-full border px-3 py-1 text-xs font-semibold shadow-sm',
    doneAt
      ? 'border-emerald-500/50 bg-emerald-950/40 text-emerald-100 line-through'
      : 'border-indigo-500/40 bg-indigo-950/50 text-indigo-100',
    mode === 'editable' ? 'cursor-pointer hover:border-indigo-400 hover:bg-indigo-900/60' : '',
  ].join(' ');

  const content = chunks.map((chunk, index) => (
    <span key={chunk} className="inline-flex items-center gap-1">
      {index > 0 ? <span className="text-slate-400">·</span> : null}
      <span>{chunk}</span>
    </span>
  ));

  if (mode === 'preview') {
    return (
      <div data-testid={baseTestId} className={pillClasses}>
        {content}
      </div>
    );
  }

  return (
    <div className="relative inline-flex flex-col items-start gap-2">
      <button
        type="button"
        data-testid={baseTestId}
        aria-expanded={isOpen}
        onClick={openEditor}
        onContextMenu={(event) => {
          event.preventDefault();
          openEditor();
        }}
        onPointerDown={() => {
          clearLongPress();
          longPressTimer.current = setTimeout(openEditor, 500);
        }}
        onPointerUp={clearLongPress}
        onPointerCancel={clearLongPress}
        onPointerLeave={clearLongPress}
        className={pillClasses}
      >
        {content}
      </button>

      {isOpen ? (
        <div
          data-testid={`${baseTestId}-editor`}
          className="z-20 w-72 rounded-2xl border border-slate-700 bg-slate-900 p-3 text-sm text-slate-100 shadow-xl"
        >
          <label className="block text-xs font-semibold uppercase tracking-wide text-slate-400">
            Due
            <input
              type="datetime-local"
              value={localDue}
              onChange={(event) => setLocalDue(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            />
          </label>

          <label className="mt-3 block text-xs font-semibold uppercase tracking-wide text-slate-400">
            Priority
            <select
              value={localPriority}
              onChange={(event) => {
                const value = event.target.value;
                setLocalPriority(value ? (Number(value) as DeadlinePriority) : '');
              }}
              className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            >
              <option value="">Unset</option>
              <option value="1">High</option>
              <option value="2">Medium</option>
              <option value="3">Low</option>
            </select>
          </label>

          <label className="mt-3 block text-xs font-semibold uppercase tracking-wide text-slate-400">
            Recurring
            <select
              value={localRecurring}
              onChange={(event) => setLocalRecurring(event.target.value as DeadlineRecurring | '')}
              className="mt-1 w-full rounded-lg border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            >
              <option value="">Unset</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </label>

          <div className="mt-3 flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={() => void markDone()}
              className="rounded-lg border border-slate-600 px-2.5 py-1 text-xs font-semibold text-slate-200 hover:border-emerald-500 hover:text-emerald-200"
            >
              {doneAt ? 'Mark not done' : 'Mark done'}
            </button>
            <button
              type="button"
              onClick={() => void clearAll()}
              className="rounded-lg border border-slate-600 px-2.5 py-1 text-xs font-semibold text-slate-200 hover:border-red-500 hover:text-red-200"
            >
              Clear
            </button>
            <button
              type="button"
              onClick={() => void saveChanges()}
              className="rounded-lg bg-indigo-600 px-3 py-1 text-xs font-semibold text-white hover:bg-indigo-500"
            >
              Save
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default DeadlinePill;
