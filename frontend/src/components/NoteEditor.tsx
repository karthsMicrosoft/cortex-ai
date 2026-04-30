import { useCallback, useState } from 'react';
import { X, Plus } from 'lucide-react';
import type { Category } from '../api/notes';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const CATEGORIES: Category[] = [
  'Music',
  'Fitness',
  'Journal',
  'Ideas',
  'Spiritual',
  'Learning',
];

const COMMON_MOODS = ['Happy', 'Focused', 'Reflective', 'Anxious', 'Energetic', 'Calm', 'Sad'];

// ---------------------------------------------------------------------------
// Note shape accepted by NoteEditor (minimal — works for both LocalNoteWithAI and NoteOut)
// ---------------------------------------------------------------------------

export interface NoteEditorNote {
  id?: string;
  serverId?: string;
  content: string;
  category: Category;
  tags?: string[];
  mood?: string;
  music_metadata?: Record<string, unknown>;
  processing_status?: string;
  processingStatus?: string;
  /** Field names whose current value was populated by AI (not yet overridden by user) */
  aiSuggestedFields?: string[];
}

// ---------------------------------------------------------------------------
// Patch shape (NoteUpdate semantics — only changed fields)
// ---------------------------------------------------------------------------

export interface NotePatch {
  content?: string;
  category?: Category;
  tags?: string[];
  mood?: string;
  music_metadata?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// AI-suggested badge
// ---------------------------------------------------------------------------

function AISuggestedBadge(): React.ReactElement {
  return (
    <span className="ml-1.5 inline-flex items-center rounded-full bg-indigo-900/60 px-1.5 py-0.5 text-[10px] font-medium text-indigo-300 border border-indigo-700">
      AI suggested
    </span>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface NoteEditorProps {
  note: NoteEditorNote;
  /** Called with only the changed fields (NoteUpdate semantics) */
  onSave: (patch: NotePatch) => Promise<void>;
  /** Called when the user cancels */
  onCancel: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * NoteEditor — inline editor for category, tags, mood, music_metadata.
 *
 * B8 compliance:
 *  - Each AI-populated field (listed in note.aiSuggestedFields) shows an
 *    "AI-suggested" badge until the user edits it.
 *  - On save, only changed fields are sent (NoteUpdate / exclude_unset semantics).
 *  - Manual edits to category/tags/mood/music_metadata do NOT trigger
 *    pipeline re-run (mitigation #6) — processingStatus is never set in the patch.
 */
export function NoteEditor({ note, onSave, onCancel }: NoteEditorProps): React.ReactElement {
  const [content, setContent] = useState(note.content);
  const [category, setCategory] = useState<Category>(note.category);
  const [tags, setTags] = useState<string[]>(note.tags ?? []);
  const [tagInput, setTagInput] = useState('');
  const [mood, setMood] = useState(note.mood ?? '');
  const [musicMeta, setMusicMeta] = useState<Record<string, unknown>>(
    note.music_metadata ?? {},
  );

  // Track which AI-suggested fields the user has already edited
  const [userEditedFields, setUserEditedFields] = useState<Set<string>>(new Set());

  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // A field shows "AI suggested" if it was in aiSuggestedFields AND the user
  // hasn't edited it yet
  const isAISuggested = (field: string) =>
    (note.aiSuggestedFields ?? []).includes(field) && !userEditedFields.has(field);

  const markEdited = (field: string) => {
    setUserEditedFields((prev) => {
      if (prev.has(field)) return prev;
      const next = new Set(prev);
      next.add(field);
      return next;
    });
  };

  // ------------------------------------------------------------------ tags

  const addTag = useCallback(() => {
    const trimmed = tagInput.trim().toLowerCase();
    if (trimmed && !tags.includes(trimmed)) {
      setTags((prev) => [...prev, trimmed]);
      markEdited('tags');
    }
    setTagInput('');
  }, [tagInput, tags]);

  const removeTag = useCallback((tag: string) => {
    setTags((prev) => prev.filter((t) => t !== tag));
    markEdited('tags');
  }, []);

  // ------------------------------------------------------------------ music_metadata chips

  const updateMusicField = useCallback((key: string, value: string) => {
    setMusicMeta((prev) => ({ ...prev, [key]: value }));
    markEdited('music_metadata');
  }, []);

  // ------------------------------------------------------------------ save

  const handleSave = useCallback(async () => {
    setIsSaving(true);
    setSaveError(null);

    // Build partial patch — only changed fields (exclude_unset semantics, mitigation #6)
    const patch: NotePatch = {};
    if (content !== note.content) patch.content = content;
    if (category !== note.category) patch.category = category;
    if (JSON.stringify(tags) !== JSON.stringify(note.tags ?? [])) patch.tags = tags;
    if (mood !== (note.mood ?? '')) patch.mood = mood || undefined;
    if (
      category === 'Music' &&
      JSON.stringify(musicMeta) !== JSON.stringify(note.music_metadata ?? {})
    ) {
      patch.music_metadata = musicMeta;
    }

    // NOTE: processingStatus is NEVER included in the patch (mitigation #6)

    try {
      await onSave(patch);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setIsSaving(false);
    }
  }, [note, content, category, tags, mood, musicMeta, onSave]);

  // ------------------------------------------------------------------ render

  return (
    <div className="space-y-5 rounded-xl border border-slate-700 bg-slate-800/60 p-5">
      {/* Content */}
      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400">
          Content
          {isAISuggested('content') && <AISuggestedBadge />}
        </label>
        <textarea
          className="w-full rounded-lg border border-slate-600 bg-slate-900 p-3 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          rows={5}
          value={content}
          onChange={(e) => {
            setContent(e.target.value);
            markEdited('content');
          }}
          placeholder="Note content…"
        />
      </div>

      {/* Category */}
      <div>
        <label
          htmlFor="note-editor-category"
          className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400"
        >
          Category
          {isAISuggested('category') && <AISuggestedBadge />}
        </label>
        <select
          id="note-editor-category"
          aria-label="Category"
          className="w-full rounded-lg border border-slate-600 bg-slate-900 p-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value as Category);
            markEdited('category');
          }}
        >
          {CATEGORIES.map((cat) => (
            <option key={cat} value={cat}>
              {cat}
            </option>
          ))}
        </select>
      </div>

      {/* Tags */}
      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400">
          Tags
          {isAISuggested('tags') && <AISuggestedBadge />}
        </label>
        <div className="mb-2 flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center gap-1 rounded-full bg-slate-700 px-2 py-0.5 text-xs text-slate-200"
            >
              {tag}
              <button
                type="button"
                aria-label={`Remove tag ${tag}`}
                onClick={() => removeTag(tag)}
                className="ml-0.5 rounded-full text-slate-400 hover:text-red-400 focus:outline-none"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            className="flex-1 rounded-lg border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            placeholder="Add tag…"
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addTag();
              }
            }}
          />
          <button
            type="button"
            onClick={addTag}
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            aria-label="Add tag"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Mood */}
      <div>
        <label
          htmlFor="note-editor-mood"
          className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400"
        >
          Mood
          {isAISuggested('mood') && <AISuggestedBadge />}
        </label>
        <div className="mb-2 flex flex-wrap gap-1.5">
          {COMMON_MOODS.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => {
                setMood(m);
                markEdited('mood');
              }}
              className={[
                'rounded-full border px-3 py-0.5 text-xs transition-colors',
                mood === m
                  ? 'border-indigo-500 bg-indigo-900/50 text-indigo-200'
                  : 'border-slate-600 bg-slate-800 text-slate-400 hover:border-slate-500',
              ].join(' ')}
            >
              {m}
            </button>
          ))}
        </div>
        <input
          id="note-editor-mood"
          type="text"
          className="w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder="Or type a mood…"
          value={mood}
          onChange={(e) => {
            setMood(e.target.value);
            markEdited('mood');
          }}
        />
      </div>

      {/* Music metadata — only when category='Music' */}
      {category === 'Music' && (
        <div data-testid="music-metadata">
          <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-slate-400">
            Music Details
            {isAISuggested('music_metadata') && <AISuggestedBadge />}
          </label>
          <div className="grid grid-cols-2 gap-3">
            {(
              [
                { key: 'tempo_guess', label: 'Tempo' },
                { key: 'key_guess', label: 'Key' },
                { key: 'genre', label: 'Genre' },
                { key: 'instruments', label: 'Instruments' },
              ] as const
            ).map(({ key, label }) => (
              <div key={key}>
                <label
                  htmlFor={`music-${key}`}
                  className="mb-0.5 block text-xs text-slate-500"
                >
                  {label}
                </label>
                <input
                  id={`music-${key}`}
                  type="text"
                  aria-label={label}
                  className="w-full rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  placeholder={`${label}…`}
                  value={String(
                    musicMeta[key] ??
                      musicMeta[key.replace('_guess', '')] ??
                      '',
                  )}
                  onChange={(e) => updateMusicField(key, e.target.value)}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Error */}
      {saveError && (
        <p className="text-sm text-red-400" role="alert">
          {saveError}
        </p>
      )}

      {/* Actions */}
      <div className="flex gap-3">
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 rounded-lg border border-slate-600 py-2 text-sm font-semibold text-slate-300 transition-colors hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-400"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={isSaving}
          className="flex-1 rounded-lg bg-indigo-600 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:opacity-50"
        >
          {isSaving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  );
}

export default NoteEditor;
