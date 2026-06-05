import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ChevronDown, ChevronRight, LayoutGrid, Music, Pencil, Plus, Check, X, Trash2 } from 'lucide-react';
import { db } from '../db';
import type { LocalNote } from '../db';
import { deleteNote, getNote, updateNote as updateNoteDetails } from '../api/notes';
import type { NoteOut } from '../api/notes';
import { searchSimilar } from '../api/search';
import type { SearchResult } from '../api/search';
import { deleteLink, getNoteLinks } from '../api/links';
import type { NoteLinkItem, NoteLinksResponse } from '../api/links';
import { LinkPicker } from '../components/LinkPicker';
import { NoteEditor } from '../components/NoteEditor';
import { ProcessingBadge } from '../components/ProcessingBadge';
import { MusicPlayer } from '../components/MusicPlayer';
import type { MusicMetadata } from '../components/MusicPlayer';
import { ShadowReaderPrompt } from '../components/ShadowReaderPrompt';
import { WikiContent } from '../components/WikiContent';
import { DeadlinePill } from '../components/DeadlinePill';
import { AddToCanvasModal } from '../components/AddToCanvasModal';
import { toggleDone, updateNote as updateTaskNote } from '../services/api/tasks';
import type { TaskNoteUpdate } from '../services/api/tasks';
import { CATEGORY_COLORS, formatDateTime } from '../utils/formatters';
import { isCanvasEnabled } from '../featureFlags';

// ---------------------------------------------------------------------------
// Music metadata label editor
// ---------------------------------------------------------------------------

interface MusicLabelEditorProps {
  noteId: string;
  metadata: MusicMetadata;
  onSaved: (updated: NoteOut) => void;
}

function MusicLabelEditor({ noteId, metadata, onSaved }: MusicLabelEditorProps): React.ReactElement {
  const [isEditing, setIsEditing] = useState(false);
  const [tempo, setTempo] = useState(String(metadata.tempo ?? ''));
  const [key, setKey] = useState(metadata.key ?? '');
  const [genre, setGenre] = useState(metadata.genre ?? '');
  const [mood, setMood] = useState(metadata.mood ?? '');
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleSave = async () => {
    setIsSaving(true);
    setSaveError(null);
    try {
      const updated = await updateNoteDetails(noteId, {
        music_metadata: {
          ...(tempo ? { tempo: Number(tempo) } : {}),
          ...(key ? { key } : {}),
          ...(genre ? { genre } : {}),
          ...(mood ? { mood } : {}),
        },
      });
      onSaved(updated);
      setIsEditing(false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setTempo(String(metadata.tempo ?? ''));
    setKey(metadata.key ?? '');
    setGenre(metadata.genre ?? '');
    setMood(metadata.mood ?? '');
    setSaveError(null);
    setIsEditing(false);
  };

  if (!isEditing) {
    return (
      <button
        type="button"
        onClick={() => setIsEditing(true)}
        className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300"
        aria-label="Edit music labels"
      >
        <Pencil className="h-3 w-3" aria-hidden="true" />
        Edit labels
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-slate-700 bg-slate-900/60 p-3">
      <p className="text-xs font-semibold text-slate-400">Edit Music Labels</p>
      <div className="grid grid-cols-2 gap-2">
        {[
          { label: 'BPM', value: tempo, setter: setTempo, type: 'number' as const },
          { label: 'Key', value: key, setter: setKey, type: 'text' as const },
          { label: 'Genre', value: genre, setter: setGenre, type: 'text' as const },
          { label: 'Mood', value: mood, setter: setMood, type: 'text' as const },
        ].map(({ label, value, setter, type }) => (
          <label key={label} className="flex flex-col gap-0.5">
            <span className="text-xs text-slate-500">{label}</span>
            <input
              type={type}
              value={value}
              onChange={(e) => setter(e.target.value)}
              className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none"
              aria-label={label}
            />
          </label>
        ))}
      </div>
      {saveError && <p className="text-xs text-red-400">{saveError}</p>}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={isSaving}
          className="flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          <Check className="h-3 w-3" aria-hidden="true" />
          {isSaving ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          onClick={handleCancel}
          className="flex items-center gap-1 rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-400 hover:text-slate-200"
        >
          <X className="h-3 w-3" aria-hidden="true" />
          Cancel
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Backlinks panel (PR 6.1)
// ---------------------------------------------------------------------------

interface BacklinksPanelProps {
  noteId: string;
  /** Pre-fetched links data from parent. When provided, the panel skips its
   *  own initial fetch and uses this instead. PR 6.5 — page-level eager fetch
   *  so wiki refs in note.content can be rendered as clickable links without
   *  waiting for the panel to expand. */
  preloadedData?: NoteLinksResponse | null;
  /** Optional callback to ask the parent to refresh the shared links data
   *  (after manual link create/remove). When provided, the panel calls this
   *  instead of fetching itself. */
  onRefresh?: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Title editor (PR 6.4) — H1 with click-to-edit inline input.
// ---------------------------------------------------------------------------

const TITLE_MAX = 120;

interface TitleEditorProps {
  noteId: string;
  title: string | null | undefined;
  isDone?: boolean;
  onSaved: (updated: NoteOut) => void;
}

function TitleEditor({ noteId, title, isDone = false, onSaved }: TitleEditorProps): React.ReactElement {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(title ?? '');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const enterEdit = () => {
    setDraft(title ?? '');
    setError(null);
    setIsEditing(true);
  };

  const cancel = () => {
    setError(null);
    setIsEditing(false);
  };

  const save = async () => {
    const next = draft.trim();
    setIsSaving(true);
    setError(null);
    try {
      const updated = await updateNoteDetails(noteId, { title: next.length > 0 ? next : null });
      onSaved(updated);
      setIsEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setIsSaving(false);
    }
  };

  if (!isEditing) {
    const hasTitle = !!(title && title.trim().length > 0);
    return (
      <h1
        role="heading"
        aria-level={1}
        tabIndex={0}
        onClick={enterEdit}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') enterEdit();
        }}
        className={[
          'cursor-text text-2xl font-semibold leading-tight focus:outline-none focus:ring-2 focus:ring-indigo-400 rounded-md px-1 -mx-1',
          hasTitle ? 'text-slate-100' : 'text-slate-500 italic',
          isDone ? 'line-through decoration-emerald-400/80' : '',
        ].join(' ')}
        title="Click to edit title"
      >
        {hasTitle ? title : 'Untitled note'}
      </h1>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <input
          ref={inputRef}
          type="text"
          role="textbox"
          aria-label="Edit note title"
          maxLength={TITLE_MAX}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              void save();
            } else if (e.key === 'Escape') {
              e.preventDefault();
              cancel();
            }
          }}
          disabled={isSaving}
          placeholder="Untitled note"
          className="flex-1 rounded-md border border-slate-600 bg-slate-800 px-2 py-1 text-2xl font-semibold text-slate-100 focus:border-indigo-500 focus:outline-none"
        />
        <button
          type="button"
          aria-label="Save title"
          onClick={() => void save()}
          disabled={isSaving}
          className="rounded-md bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {isSaving ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          aria-label="Cancel title edit"
          onClick={cancel}
          disabled={isSaving}
          className="rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:text-slate-100"
        >
          Cancel
        </button>
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Aliases editor (PR 6.4) — collapsible chip list with debounced PATCH.
// ---------------------------------------------------------------------------

const ALIAS_MAX_LEN = 120;
const ALIAS_MAX_COUNT = 20;
const ALIAS_DEBOUNCE_MS = 500;

interface AliasesEditorProps {
  noteId: string;
  aliases: string[];
  onSaved: (updated: NoteOut) => void;
}

function AliasesEditor({ noteId, aliases, onSaved }: AliasesEditorProps): React.ReactElement {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<string[]>(aliases);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const initialKey = useRef(JSON.stringify(aliases));

  // Sync when the prop changes from the outside (e.g. server refresh).
  useEffect(() => {
    const key = JSON.stringify(aliases);
    if (key !== initialKey.current) {
      setItems(aliases);
      initialKey.current = key;
    }
  }, [aliases]);

  const persist = useCallback(
    (next: string[]) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        void (async () => {
          try {
            const updated = await updateNoteDetails(noteId, { aliases: next });
            onSaved(updated);
            setError(null);
          } catch (err) {
            setError(err instanceof Error ? err.message : 'Save failed');
          }
        })();
      }, ALIAS_DEBOUNCE_MS);
    },
    [noteId, onSaved],
  );

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const addAlias = () => {
    const value = draft.trim();
    if (!value) return;
    if (value.length > ALIAS_MAX_LEN) {
      setError(`Alias must be ${ALIAS_MAX_LEN} characters or fewer.`);
      return;
    }
    if (items.some((a) => a.toLowerCase() === value.toLowerCase())) {
      setDraft('');
      return;
    }
    if (items.length >= ALIAS_MAX_COUNT) {
      setError(`Maximum ${ALIAS_MAX_COUNT} aliases.`);
      return;
    }
    const next = [...items, value];
    setItems(next);
    setDraft('');
    setError(null);
    persist(next);
  };

  const removeAlias = (alias: string) => {
    const next = items.filter((a) => a !== alias);
    setItems(next);
    setError(null);
    persist(next);
  };

  return (
    <section className="flex flex-col gap-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 self-start text-xs font-semibold uppercase tracking-wide text-slate-400 hover:text-slate-200"
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="h-3 w-3" aria-hidden="true" />
        ) : (
          <ChevronRight className="h-3 w-3" aria-hidden="true" />
        )}
        Aliases {items.length > 0 && <span className="text-slate-500">({items.length})</span>}
      </button>
      {open && (
        <div className="flex flex-col gap-2 rounded-lg border border-slate-800 bg-slate-900/40 p-3">
          {items.length === 0 && (
            <p className="text-xs text-slate-500">
              No aliases yet. Add other names this note can be linked under.
            </p>
          )}
          {items.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {items.map((alias) => (
                <span
                  key={alias}
                  className="inline-flex items-center gap-1 rounded-full bg-slate-700 px-2 py-0.5 text-xs text-slate-200"
                >
                  {alias}
                  <button
                    type="button"
                    aria-label={`Remove alias ${alias}`}
                    onClick={() => removeAlias(alias)}
                    className="rounded-full text-slate-400 hover:text-red-300 focus:outline-none"
                  >
                    <X className="h-3 w-3" aria-hidden="true" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="flex items-center gap-2">
            <input
              type="text"
              role="textbox"
              aria-label="Add alias"
              value={draft}
              maxLength={ALIAS_MAX_LEN}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  addAlias();
                }
              }}
              placeholder="+ Add alias"
              className="flex-1 rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={addAlias}
              disabled={!draft.trim()}
              className="rounded-md bg-indigo-600 px-2 py-1 text-xs text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              Add
            </button>
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>
      )}
    </section>
  );
}

function toDatetimeLocalInput(value?: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

type TaskFeedback = { kind: 'success' | 'error'; message: string };

interface TaskPanelProps {
  note: NoteOut;
  onUpdated: (updated: NoteOut) => void;
}

function TaskPanel({ note, onUpdated }: TaskPanelProps): React.ReactElement {
  const [isAdding, setIsAdding] = useState(false);
  const [draftDue, setDraftDue] = useState('');
  const [draftPriority, setDraftPriority] = useState<1 | 2 | 3 | ''>('');
  const [draftRecurring, setDraftRecurring] = useState<'daily' | 'weekly' | 'monthly' | ''>('');
  const [isSaving, setIsSaving] = useState(false);
  const [feedback, setFeedback] = useState<TaskFeedback | null>(null);

  const hasDeadlineSignal = note.due_at != null || note.priority != null || note.recurring != null;
  const isFullyEmpty = !hasDeadlineSignal && note.done_at == null;
  const canSaveDraft = draftDue !== '' || draftPriority !== '' || draftRecurring !== '';

  const applyTaskUpdate = useCallback(
    async (changes: TaskNoteUpdate) => {
      setIsSaving(true);
      setFeedback(null);
      try {
        const updated = (await updateTaskNote(note.id, changes)) as NoteOut | undefined;
        onUpdated(updated ?? { ...note, ...changes, updated_at: new Date().toISOString() });
        setIsAdding(false);
        setFeedback({ kind: 'success', message: 'Reminder updated.' });
      } catch (err) {
        setFeedback({
          kind: 'error',
          message: err instanceof Error ? err.message : 'Could not update reminder.',
        });
      } finally {
        setIsSaving(false);
      }
    },
    [note, onUpdated],
  );

  const handleAddReminder = useCallback(() => {
    setDraftDue(toDatetimeLocalInput(note.due_at));
    setDraftPriority(note.priority ?? '');
    setDraftRecurring(note.recurring ?? '');
    setFeedback(null);
    setIsAdding(true);
  }, [note.due_at, note.priority, note.recurring]);

  const handleSaveDraft = useCallback(async () => {
    await applyTaskUpdate({
      due_at: draftDue ? new Date(draftDue).toISOString() : null,
      priority: draftPriority === '' ? null : draftPriority,
      recurring: draftRecurring === '' ? null : draftRecurring,
    });
  }, [applyTaskUpdate, draftDue, draftPriority, draftRecurring]);

  const handleToggleDone = useCallback(async () => {
    setIsSaving(true);
    setFeedback(null);
    try {
      const updated = (await toggleDone(note.id)) as NoteOut | undefined;
      const fallbackDoneAt = note.done_at ? null : new Date().toISOString();
      onUpdated(updated ?? { ...note, done_at: fallbackDoneAt, updated_at: new Date().toISOString() });
      setFeedback({
        kind: 'success',
        message: note.done_at ? 'Marked not done.' : 'Marked done.',
      });
    } catch (err) {
      setFeedback({
        kind: 'error',
        message: err instanceof Error ? err.message : 'Could not update task status.',
      });
    } finally {
      setIsSaving(false);
    }
  }, [note, onUpdated]);

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-3" aria-label="Task">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Task</span>
          {hasDeadlineSignal ? (
            <DeadlinePill
              mode="editable"
              dueAt={note.due_at ?? null}
              priority={note.priority ?? null}
              recurring={note.recurring ?? null}
              doneAt={note.done_at ?? null}
              testId="note-detail-deadline-pill"
              onUpdate={applyTaskUpdate}
            />
          ) : note.done_at ? (
            <span className="rounded-full border border-emerald-500/50 bg-emerald-950/40 px-3 py-1 text-xs font-semibold text-emerald-100 line-through">
              Done
            </span>
          ) : null}
          {isFullyEmpty && !isAdding && (
            <button
              type="button"
              onClick={handleAddReminder}
              className="rounded-full border border-dashed border-indigo-500/60 px-3 py-1 text-xs font-semibold text-indigo-200 hover:bg-indigo-950/50"
            >
              + Add reminder
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={() => void handleToggleDone()}
          disabled={isSaving}
          className="self-start rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:border-emerald-500 hover:text-emerald-200 disabled:opacity-50 sm:self-auto"
        >
          {note.done_at ? 'Mark not done' : 'Mark done'}
        </button>
      </div>

      {isAdding && (
        <div data-testid="note-detail-task-editor" className="mt-3 grid gap-3 rounded-lg border border-slate-800 bg-slate-950/40 p-3 sm:grid-cols-3">
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Due
            <input
              type="datetime-local"
              value={draftDue}
              onChange={(event) => setDraftDue(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            />
          </label>
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Priority
            <select
              value={draftPriority}
              onChange={(event) => {
                const value = event.target.value;
                setDraftPriority(value ? (Number(value) as 1 | 2 | 3) : '');
              }}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            >
              <option value="">Unset</option>
              <option value="1">High</option>
              <option value="2">Medium</option>
              <option value="3">Low</option>
            </select>
          </label>
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Recurring
            <select
              value={draftRecurring}
              onChange={(event) => setDraftRecurring(event.target.value as 'daily' | 'weekly' | 'monthly' | '')}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            >
              <option value="">Unset</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </label>
          <div className="flex gap-2 sm:col-span-3">
            <button
              type="button"
              onClick={() => void handleSaveDraft()}
              disabled={isSaving || !canSaveDraft}
              className="rounded-lg bg-indigo-600 px-3 py-1 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {isSaving ? 'Saving…' : 'Save reminder'}
            </button>
            <button
              type="button"
              onClick={() => setIsAdding(false)}
              disabled={isSaving}
              className="rounded-lg border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-300 hover:text-slate-100 disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {feedback && (
        <p className={feedback.kind === 'error' ? 'mt-2 text-xs text-red-400' : 'mt-2 text-xs text-emerald-400'}>
          {feedback.message}
        </p>
      )}
    </section>
  );
}

function _displayLabel(item: NoteLinkItem): string {
  if (item.title && item.title.trim().length > 0) return item.title;
  return '(untitled note)';
}

function BacklinkCard({
  item,
  onClick,
  onRemove,
  isRemoving,
}: {
  item: NoteLinkItem;
  onClick: (id: string) => void;
  onRemove?: () => void;
  isRemoving?: boolean;
}): React.ReactElement {
  return (
    <div className="group relative">
      <button
        type="button"
        onClick={() => onClick(item.note_id)}
        className="w-full rounded-xl border border-slate-700 bg-slate-800/40 p-3 text-left transition-colors hover:border-indigo-500/50 focus:outline-none focus:ring-2 focus:ring-indigo-400"
      >
        <p className="line-clamp-2 text-sm text-slate-200">{_displayLabel(item)}</p>
        <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
          <span className="rounded bg-slate-700/60 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-300">
            via {item.link_type}
          </span>
          <span>{item.category}</span>
          {item.link_type === 'semantic' && item.score !== null && (
            <>
              <span>·</span>
              <span>{(item.score * 100).toFixed(0)}%</span>
            </>
          )}
        </div>
      </button>
      {onRemove && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          disabled={isRemoving}
          aria-label="Remove manual link"
          className="absolute right-2 top-2 rounded-md p-1 text-slate-500 hover:bg-slate-700/60 hover:text-red-300 focus:opacity-100 disabled:opacity-50"
        >
          <X className="h-3 w-3" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

function BacklinksPanel({
  noteId,
  preloadedData,
  onRefresh,
}: BacklinksPanelProps): React.ReactElement {
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const [data, setData] = useState<NoteLinksResponse | null>(preloadedData ?? null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [removingLinkId, setRemovingLinkId] = useState<string | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);

  // Mirror parent-provided data into local state so updates from the page
  // (e.g. after a refresh) propagate into the panel.
  useEffect(() => {
    if (preloadedData !== undefined) {
      setData(preloadedData);
    }
  }, [preloadedData]);

  const load = useCallback(async () => {
    if (onRefresh) {
      // Parent owns the data — delegate.
      setIsLoading(true);
      setError(null);
      try {
        await onRefresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load links');
      } finally {
        setIsLoading(false);
      }
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const resp = await getNoteLinks(noteId);
      setData(resp);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load links');
    } finally {
      setIsLoading(false);
    }
  }, [noteId, onRefresh]);

  const handleToggle = useCallback(() => {
    const next = !expanded;
    setExpanded(next);
    if (next && data === null && !isLoading) {
      void load();
    }
  }, [expanded, data, isLoading, load]);

  const handleOpenPicker = useCallback(() => {
    // Make sure the panel is expanded so the user sees the new link land.
    if (!expanded) {
      setExpanded(true);
      if (data === null && !isLoading) void load();
    }
    setPickerOpen(true);
  }, [expanded, data, isLoading, load]);

  const handleLinkCreated = useCallback(() => {
    // Refresh the panel so the new manual link appears in outgoing.
    void load();
  }, [load]);

  const handleRemove = useCallback(
    async (item: NoteLinkItem) => {
      if (!item.link_id || removingLinkId) return;
      setRemovingLinkId(item.link_id);
      setRemoveError(null);
      try {
        await deleteLink(noteId, item.link_id);
        await load();
      } catch (err) {
        setRemoveError(err instanceof Error ? err.message : 'Could not remove link');
      } finally {
        setRemovingLinkId(null);
      }
    },
    [noteId, removingLinkId, load],
  );

  return (
    <section aria-label="Backlinks">
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={handleToggle}
          aria-expanded={expanded}
          className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400 hover:text-slate-200"
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-3 w-3" aria-hidden="true" />
          )}
          Backlinks
        </button>
        <button
          type="button"
          onClick={handleOpenPicker}
          className="flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-[11px] text-slate-300 hover:border-indigo-500/60 hover:text-indigo-200"
        >
          <Plus className="h-3 w-3" aria-hidden="true" />
          Link to another note
        </button>
      </div>

      {expanded && (
        <div className="mt-3 flex flex-col gap-3" data-testid="backlinks-body">
          {removeError && (
            <p role="alert" className="text-xs text-red-400">
              {removeError}
            </p>
          )}

          {isLoading && (
            <div className="flex flex-col gap-2" aria-label="Loading backlinks">
              <div className="h-12 animate-pulse rounded-xl bg-slate-800/60" />
              <div className="h-12 animate-pulse rounded-xl bg-slate-800/60" />
            </div>
          )}

          {error && !isLoading && (
            <div className="flex items-center justify-between rounded-xl border border-red-700/40 bg-red-900/20 p-3 text-xs text-red-300">
              <span>{error}</span>
              <button
                type="button"
                onClick={() => void load()}
                className="rounded-md border border-red-700/60 px-2 py-1 text-red-200 hover:bg-red-900/40"
              >
                Retry
              </button>
            </div>
          )}

          {data && !isLoading && !error && (
            <>
              {/* Incoming first — Obsidian's primary backlinks UI */}
              <div>
                <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  Notes linking here ({data.incoming.length})
                </h3>
                {data.incoming.length === 0 ? (
                  <p className="text-xs text-slate-500">
                    No notes link to this one yet.
                  </p>
                ) : (
                  <div className="flex flex-col gap-2">
                    {data.incoming.map((item) => (
                      <BacklinkCard
                        key={`in-${item.link_id ?? item.note_id}-${item.link_type}`}
                        item={item}
                        onClick={(id) => navigate(`/note/${id}`)}
                      />
                    ))}
                  </div>
                )}
              </div>

              {data.outgoing.length > 0 && (
                <div>
                  <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                    Links from this note ({data.outgoing.length})
                  </h3>
                  <div className="flex flex-col gap-2">
                    {data.outgoing.map((item) => (
                      <BacklinkCard
                        key={`out-${item.link_id ?? item.note_id}-${item.link_type}`}
                        item={item}
                        onClick={(id) => navigate(`/note/${id}`)}
                        onRemove={
                          item.link_type === 'manual' && item.link_id
                            ? () => void handleRemove(item)
                            : undefined
                        }
                        isRemoving={
                          item.link_id !== null && removingLinkId === item.link_id
                        }
                      />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {pickerOpen && (
        <LinkPicker
          sourceNoteId={noteId}
          onClose={() => setPickerOpen(false)}
          onCreated={handleLinkCreated}
        />
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// NoteDetailPage
// ---------------------------------------------------------------------------

/**
 * NoteDetailPage — full note view.
 *
 * US-6 additions:
 * - MusicPlayer rendered for voice+Music notes (Task 6.2)
 * - music_metadata chips (tempo, key, genre, mood) (Task 6.2)
 * - Chip-style label editor for music metadata (Task 6.3)
 */
export default function NoteDetailPage(): React.ReactElement {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [localNote, setLocalNote] = useState<LocalNote | null>(null);
  const [serverNote, setServerNote] = useState<NoteOut | null>(null);
  const [similar, setSimilar] = useState<SearchResult[]>([]);
  const [linksData, setLinksData] = useState<NoteLinksResponse | null>(null);
  const [wikiLinks, setWikiLinks] = useState<Map<string, { id: string; title: string }>>(
    new Map(),
  );
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [addToCanvasOpen, setAddToCanvasOpen] = useState(false);
  const [canvasToast, setCanvasToast] = useState<{ canvasId: string; title: string } | null>(null);

  useEffect(() => {
    if (!canvasToast) return;
    const t = window.setTimeout(() => setCanvasToast(null), 3000);
    return () => window.clearTimeout(t);
  }, [canvasToast]);

  // PR 6.5 — shared link loader. Builds both the BacklinksPanel data and
  // the wiki-resolution map from a single API call.
  const refreshLinks = useCallback(
    async (sId: string): Promise<void> => {
      const resp = await getNoteLinks(sId);
      setLinksData(resp);
      const map = new Map<string, { id: string; title: string }>();
      for (const item of resp.outgoing) {
        if (item.link_type === 'wiki' && item.title) {
          map.set(item.title.toLowerCase(), {
            id: item.note_id,
            title: item.title,
          });
        }
      }
      setWikiLinks(map);
    },
    [],
  );

  // Load note
  useEffect(() => {
    if (!id) return;

    void (async () => {
      setIsLoading(true);
      try {
        // 2026-05-01 fix (bug 7): the URL :id param can be EITHER a localId
        // (when navigated from Library/NoteCard) OR a serverId (when the
        // user clicked a Related Note card whose `rel.id` is the serverId).
        // Try localId first, then fall back to serverId lookup, then to a
        // direct backend fetch for server-only views.
        let local = await db.notes.get(id);
        if (!local) {
          local = await db.notes.where('serverId').equals(id).first();
        }
        if (local) setLocalNote(local);

        // Resolve the serverId for backend calls. Use the local row's
        // serverId when present; otherwise treat the URL param as the
        // serverId directly (related-note click).
        const sId = local?.serverId ?? (local ? undefined : id);
        if (sId) {
          try {
            const server = await getNote(sId);
            setServerNote(server);
          } catch {
            // Offline or backend hiccup — local row is still rendered.
          }
          try {
            const rel = await searchSimilar(sId);
            setSimilar(rel.slice(0, 5));
          } catch {
            // Non-critical
          }
          // PR 6.5 — fetch outgoing wiki links so [[Title]] refs render as
          // clickable links via WikiContent. Failure is non-critical.
          try {
            await refreshLinks(sId);
          } catch {
            // Non-critical — refs will render as plain [[text]] when missing.
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load note');
      } finally {
        setIsLoading(false);
      }
    })();
  }, [id, refreshLinks]);

  const handleSaved = useCallback((updated: NoteOut) => {
    setServerNote(updated);
  }, []);

  // 2026-05-01 fix (bugs 4 + 5): real Save handler — PUT /api/notes/{serverId}
  // with the patch, then refresh local + server state and navigate back.
  // Cancel returns to wherever the user came from.
  const handleEditorSave = useCallback(
    async (patch: import('../components/NoteEditor').NotePatch): Promise<void> => {
      const targetServerId = serverNote?.id ?? localNote?.serverId;
      if (!targetServerId) {
        throw new Error('Cannot save — note is not yet synced.');
      }
      const updated = await updateNoteDetails(targetServerId, patch);
      setServerNote(updated);
      // Mirror into Dexie so Library reflects the new category/tags/mood
      if (localNote) {
        await db.notes.update(localNote.localId, {
          category: updated.category as LocalNote['category'],
          tags: Array.isArray(updated.tags) ? (updated.tags as string[]) : localNote.tags,
          mood: typeof updated.mood === 'string' ? updated.mood : localNote.mood,
          content: updated.content ?? localNote.content,
          updatedAt: new Date(String(updated.updated_at ?? Date.now())),
        });
      }
    },
    [serverNote, localNote],
  );

  const handleEditorCancel = useCallback(() => {
    navigate(-1);
  }, [navigate]);

  const handleDelete = useCallback(async () => {
    const targetServerId = serverNote?.id ?? localNote?.serverId;
    if (!window.confirm('Delete this note? This cannot be undone.')) return;
    try {
      if (targetServerId) {
        await deleteNote(targetServerId);
      }
      if (localNote) {
        await db.notes.delete(localNote.localId);
      }
      navigate('/library', { replace: true });
    } catch (err) {
      window.alert(err instanceof Error ? err.message : 'Delete failed');
    }
  }, [serverNote, localNote, navigate]);

  // ------------------------------------------------------------------ render

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0F172A]">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  if (error || (!localNote && !serverNote)) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#0F172A]">
        <p className="text-sm text-red-400">{error ?? 'Note not found'}</p>
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="text-sm text-indigo-400 underline"
        >
          Go back
        </button>
      </div>
    );
  }

  const category = serverNote?.category ?? localNote?.category ?? 'Ideas';
  const colors = CATEGORY_COLORS[category];
  const processingStatus =
    serverNote?.processing_status ?? localNote?.processingStatus ?? 'raw';
  const tags = serverNote?.tags ?? localNote?.tags ?? [];
  const audioUrl = serverNote?.audio_url;
  // Bug 9 fix (2026-05-01): show the uploaded image when image_url is present.
  // Falls back to the local imageBlob (object URL) for offline-still-pending notes.
  const imageUrl = serverNote?.image_url;
  const sourceType = serverNote?.source_type ?? localNote?.sourceType;
  const createdAt = serverNote?.created_at ?? localNote?.createdAt.toISOString() ?? '';
  const updatedAt = serverNote?.updated_at ?? localNote?.updatedAt.toISOString() ?? '';

  // Determine if we should show MusicPlayer (voice + Music category)
  const isMusicNote = category === 'Music' && sourceType === 'voice' && !!audioUrl;

  // Extract music_metadata from server note
  const rawMeta = serverNote?.music_metadata ?? {};
  const musicMetadata: MusicMetadata = {
    tempo: typeof rawMeta.tempo === 'number' ? rawMeta.tempo : undefined,
    key: typeof rawMeta.key === 'string' ? rawMeta.key : undefined,
    genre: typeof rawMeta.genre === 'string' ? rawMeta.genre : undefined,
    mood: typeof rawMeta.mood === 'string' ? rawMeta.mood : undefined,
  };

  return (
    <div className="flex min-h-screen flex-col bg-[#0F172A] pb-24">
      {/* Header */}
      <header className="flex items-center gap-3 border-b border-slate-700 px-4 py-3">
        <button
          type="button"
          aria-label="Go back"
          onClick={() => navigate(-1)}
          className="rounded-lg p-1 text-slate-400 hover:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex flex-1 items-center gap-2 overflow-hidden">
          <span
            className={[
              'shrink-0 rounded-full border px-2 py-0.5 text-xs font-semibold',
              colors.bg,
              colors.text,
              colors.border,
            ].join(' ')}
          >
            {category}
          </span>
          <ProcessingBadge status={processingStatus as LocalNote['processingStatus']} />
        </div>
        {/* Add to Canvas (PR C) — gated by VITE_FEATURE_CANVAS (Round 28) */}
        {isCanvasEnabled() && (serverNote?.id ?? localNote?.serverId) && (
          <button
            type="button"
            aria-label="Add to canvas"
            data-testid="note-detail-add-to-canvas"
            onClick={() => setAddToCanvasOpen(true)}
            className="rounded-lg p-1 text-slate-400 hover:bg-indigo-900/30 hover:text-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          >
            <LayoutGrid className="h-5 w-5" />
          </button>
        )}
        {/* Delete button (Bug 3) — single-note delete from the detail view */}
        <button
          type="button"
          aria-label="Delete note"
          data-testid="note-detail-delete"
          onClick={() => void handleDelete()}
          className="rounded-lg p-1 text-slate-400 hover:bg-red-900/30 hover:text-red-300 focus:outline-none focus:ring-2 focus:ring-red-400"
        >
          <Trash2 className="h-5 w-5" />
        </button>
      </header>

      <main className="flex flex-1 flex-col gap-5 px-4 py-5">
        {/* Title (PR 6.4) — H1, click-to-edit. Falls back to "Untitled note". */}
        {(serverNote || localNote?.serverId) && (
          <TitleEditor
            noteId={serverNote?.id ?? (localNote?.serverId as string)}
            title={serverNote?.title ?? null}
            isDone={serverNote?.done_at != null}
            onSaved={handleSaved}
          />
        )}

        {/* Aliases (PR 6.4) — collapsible chip editor; debounced PATCH. */}
        {serverNote && (
          <AliasesEditor
            noteId={serverNote.id}
            aliases={serverNote.aliases ?? []}
            onSaved={handleSaved}
          />
        )}

        {serverNote && <TaskPanel note={serverNote} onUpdated={handleSaved} />}

        {/* Timestamps */}
        <div className="flex gap-4 text-xs text-slate-500">
          <span>Created: {formatDateTime(createdAt)}</span>
          <span>Updated: {formatDateTime(updatedAt)}</span>
        </div>

        {/* Image attachment (Bug 9) — render uploaded image for image notes */}
        {sourceType === 'image' && (imageUrl || localNote?.imageBlob) && (
          <section aria-label="Image attachment">
            <img
              src={imageUrl ?? (localNote?.imageBlob ? URL.createObjectURL(localNote.imageBlob) : '')}
              alt="Note attachment"
              className="w-full max-h-96 rounded-xl object-contain bg-slate-900 border border-slate-700"
            />
          </section>
        )}

        {/* Music player (US-6) — shown for voice + Music category notes */}
        {isMusicNote && (
          <section aria-label="Music player section">
            <MusicPlayer audioUrl={audioUrl!} metadata={musicMetadata} />
            {/* Quick label editor (US-6 Task 6.3) */}
            {serverNote && (
              <div className="mt-2">
                <MusicLabelEditor
                  noteId={serverNote.id}
                  metadata={musicMetadata}
                  onSaved={handleSaved}
                />
              </div>
            )}
          </section>
        )}

        {/* Fallback audio player for non-Music voice notes */}
        {audioUrl && !isMusicNote && (
          <div className="flex items-center gap-3 rounded-xl border border-slate-700 bg-slate-800/60 p-4">
            <Music className="h-5 w-5 text-indigo-400" aria-hidden="true" />
            <div className="flex-1">
              <p className="text-xs text-slate-400">Audio recording</p>
              <audio
                controls
                src={audioUrl}
                className="mt-1 h-8 w-full"
                aria-label="Voice recording playback"
              />
            </div>
          </div>
        )}

        {/* Tags */}
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {tags.map((tag) => (
              <span
                key={tag}
                className="rounded-full bg-slate-700 px-3 py-1 text-xs text-slate-300"
              >
                #{tag}
              </span>
            ))}
          </div>
        )}

        {/* Editor — available when serverId is known */}
        {serverNote ? (
          <>
            {/* PR 6.5 — Rendered preview with clickable [[wiki refs]] */}
            <div className="rounded-xl border border-slate-700 bg-slate-800/40 p-4">
              <p
                className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200"
                data-testid="wiki-rendered-content"
              >
                <WikiContent content={serverNote.content} wikiLinks={wikiLinks} />
              </p>
            </div>
            <NoteEditor
              note={serverNote}
              onSave={handleEditorSave}
              onCancel={handleEditorCancel}
            />
          </>
        ) : (
          <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-4">
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
              {localNote?.content ? (
                <WikiContent content={localNote.content} wikiLinks={wikiLinks} />
              ) : (
                '(recording pending transcription…)'
              )}
            </p>
            {localNote?.syncStatus === 'pending' && (
              <p className="mt-3 text-xs text-amber-400">
                This note is pending sync. Editor will be available once synced.
              </p>
            )}
          </div>
        )}

        {/* Related notes */}
        {similar.length > 0 && (
          <section>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Related Notes
            </h2>
            <div className="flex flex-col gap-2">
              {similar.map((rel) => (
                <button
                  key={rel.id}
                  type="button"
                  onClick={() => navigate(`/note/${rel.id}`)}
                  className="rounded-xl border border-slate-700 bg-slate-800/40 p-3 text-left transition-colors hover:border-indigo-500/50 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                >
                  <p className="line-clamp-2 text-sm text-slate-300">
                    {rel.content.slice(0, 120)}
                    {rel.content.length > 120 ? '…' : ''}
                  </p>
                  <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                    <span>{rel.category}</span>
                    <span>·</span>
                    <span>{(rel.combined_score * 100).toFixed(0)}% match</span>
                  </div>
                </button>
              ))}
            </div>
          </section>
        )}
        {/* Backlinks (PR 6.1) — collapsed by default; rendered below similar notes. */}
        {serverNote && (
          <BacklinksPanel
            noteId={serverNote.id}
            preloadedData={linksData}
            onRefresh={() => refreshLinks(serverNote.id)}
          />
        )}

        {/* Shadow Reader prompt (US-8) — Bug 16 (2026-05-01): auto-renders a
            bottom-sheet when status='asked'; component returns null otherwise.
            The sheet is positioned above the BottomNav so it never overlaps. */}
        {serverNote && (
          <ShadowReaderPrompt
            noteId={serverNote.id}
            onComplete={() => {
              // Refresh note to pick up answered/dismissed status
              void getNote(serverNote.id).then(setServerNote).catch(() => undefined);
            }}
          />
        )}
      </main>

      {/* Add to Canvas modal (PR C) — gated by VITE_FEATURE_CANVAS (Round 28) */}
      {isCanvasEnabled() && (serverNote?.id ?? localNote?.serverId) && (
        <AddToCanvasModal
          noteId={(serverNote?.id ?? localNote?.serverId) as string}
          noteTitle={serverNote?.title ?? undefined}
          isOpen={addToCanvasOpen}
          onClose={() => setAddToCanvasOpen(false)}
          onAdded={(canvasId) => {
            setCanvasToast({ canvasId, title: 'canvas' });
          }}
        />
      )}

      {/* Toast (PR C) — gated by VITE_FEATURE_CANVAS (Round 28) */}
      {isCanvasEnabled() && canvasToast && (
        <div
          data-testid="canvas-toast"
          className="fixed inset-x-0 top-4 z-[60] mx-auto w-fit rounded-lg border border-emerald-700 bg-emerald-900/90 px-4 py-2 text-sm text-emerald-100 shadow-lg"
        >
          Added to canvas ·{' '}
          <button
            type="button"
            className="underline hover:text-white"
            onClick={() => navigate(`/canvas/${canvasToast.canvasId}`)}
          >
            Open
          </button>
        </div>
      )}
    </div>
  );
}
