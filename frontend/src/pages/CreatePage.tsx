import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Music,
  Dumbbell,
  BookOpen,
  RefreshCw,
  Sparkles,
  X,
  Copy as CopyIcon,
  Save as SaveIcon,
} from 'lucide-react';
import { apiGet, apiPost } from '../api/client';
import type { NoteOut, NotesListResponse } from '../api/notes';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type GenerateKind = 'song' | 'practice' | 'reflection';

interface GenerateResponse {
  generated_text: string;
}

// ---------------------------------------------------------------------------
// Kind config
// ---------------------------------------------------------------------------

interface KindConfig {
  label: string;
  icon: React.ReactElement;
  description: string;
  hint: string;
  accent: string;
}

const KIND_CONFIG: Record<GenerateKind, KindConfig> = {
  song: {
    label: 'Song Idea',
    icon: <Music className="h-4 w-4" aria-hidden="true" />,
    description: 'Generate a song concept, themes, verse ideas, and a hook.',
    hint: 'Best with music or songwriting notes',
    accent: 'text-purple-400 border-purple-500 bg-purple-900/30',
  },
  practice: {
    label: 'Practice Plan',
    icon: <Dumbbell className="h-4 w-4" aria-hidden="true" />,
    description: 'Create a focused music practice session plan.',
    hint: 'Best with workout, training, or skill-practice notes',
    accent: 'text-green-400 border-green-500 bg-green-900/30',
  },
  reflection: {
    label: 'Reflection',
    icon: <BookOpen className="h-4 w-4" aria-hidden="true" />,
    description: 'Write a personal reflection that surfaces insights.',
    hint: 'Best with journal entries and personal reflection notes',
    accent: 'text-amber-400 border-amber-500 bg-amber-900/30',
  },
};

// ---------------------------------------------------------------------------
// CreatePage
// ---------------------------------------------------------------------------

export default function CreatePage(): React.ReactElement {
  const [selectedKind, setSelectedKind] = useState<GenerateKind>('song');
  const [notes, setNotes] = useState<NoteOut[]>([]);
  const [notesLoading, setNotesLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [generatedText, setGeneratedText] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);

  // Round 15 — separate error states per surface so failures don't leak.
  const [loadError, setLoadError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);

  // Round 15 — Save-as-note + copy microcopy state.
  const [copyFlash, setCopyFlash] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const generateBtnRef = useRef<HTMLButtonElement | null>(null);

  // Round 15 — extracted loader so the retry button can call it.
  const loadNotes = useCallback(() => {
    setNotesLoading(true);
    setLoadError(null);
    void apiGet<NotesListResponse>('/api/notes?limit=50')
      .then((data) => setNotes(data.items))
      .catch((err: Error) => setLoadError(err.message))
      .finally(() => setNotesLoading(false));
  }, []);

  useEffect(() => {
    loadNotes();
  }, [loadNotes]);

  const toggleNote = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // Round 15 — keyboard affordance: focus Generate after first selection so
  // Enter triggers it.
  useEffect(() => {
    if (selectedIds.size === 1 && generateBtnRef.current) {
      generateBtnRef.current.focus();
    }
  }, [selectedIds]);

  // Round 15 — mode switch must reset selections, generated text and errors.
  const changeKind = useCallback((kind: GenerateKind) => {
    setSelectedKind(kind);
    setSelectedIds(new Set());
    setGeneratedText(null);
    setValidationError(null);
    setGenerateError(null);
    setSaveError(null);
    setCopyFlash(false);
    setSavedFlash(false);
  }, []);

  const handleGenerate = useCallback(async () => {
    if (selectedIds.size === 0) {
      setValidationError('Select at least one note to generate from.');
      return;
    }
    setValidationError(null);
    setGenerateError(null);
    setIsGenerating(true);
    setGeneratedText(null);
    setSavedFlash(false);
    setCopyFlash(false);
    try {
      const result = await apiPost<GenerateResponse>('/api/ai/generate', {
        kind: selectedKind,
        source_note_ids: Array.from(selectedIds),
      });
      setGeneratedText(result.generated_text);
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : 'Generation failed.');
    } finally {
      setIsGenerating(false);
    }
  }, [selectedKind, selectedIds]);

  const handleCopy = useCallback(async () => {
    if (!generatedText) return;
    try {
      await navigator.clipboard.writeText(generatedText);
      setCopyFlash(true);
      window.setTimeout(() => setCopyFlash(false), 2000);
    } catch {
      setGenerateError('Could not copy to clipboard.');
    }
  }, [generatedText]);

  const handleSaveAsNote = useCallback(async () => {
    if (!generatedText) return;
    setIsSaving(true);
    setSaveError(null);
    setSavedFlash(false);
    try {
      await apiPost('/api/notes', {
        content: generatedText,
        source_type: 'text',
        tags: ['express', selectedKind],
      });
      setSavedFlash(true);
      window.setTimeout(() => setSavedFlash(false), 2000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Could not save note.');
    } finally {
      setIsSaving(false);
    }
  }, [generatedText, selectedKind]);

  const config = KIND_CONFIG[selectedKind];

  return (
    <div className="flex min-h-screen flex-col bg-[#0F172A] pb-24">
      {/* Header */}
      <header className="border-b border-slate-700 px-4 py-3">
        <h1 className="text-lg font-semibold text-slate-100">Create</h1>
        <p className="text-xs text-slate-400">Generate ideas from your notes</p>
      </header>

      <main className="flex flex-1 flex-col gap-5 px-4 py-4">
        {/* Kind selector */}
        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            What do you want to create?
          </h2>
          <div className="flex gap-2">
            {(Object.entries(KIND_CONFIG) as [GenerateKind, KindConfig][]).map(([kind, cfg]) => (
              <button
                key={kind}
                type="button"
                onClick={() => changeKind(kind)}
                className={[
                  'flex flex-1 flex-col items-center gap-1 rounded-xl border p-3 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-400',
                  selectedKind === kind
                    ? cfg.accent
                    : 'border-slate-700 text-slate-400 hover:border-slate-600',
                ].join(' ')}
                aria-pressed={selectedKind === kind}
              >
                {cfg.icon}
                {cfg.label}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-500">{config.description}</p>
          <p className="mt-1 text-sm text-slate-400" data-testid="mode-hint">
            {config.hint}
          </p>
        </section>

        {/* Note selector */}
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Source Notes ({selectedIds.size} selected)
            </h2>
            {selectedIds.size > 0 && (
              <button
                type="button"
                onClick={() => setSelectedIds(new Set())}
                className="flex items-center gap-0.5 text-xs text-slate-500 hover:text-slate-300"
              >
                <X className="h-3 w-3" aria-hidden="true" />
                Clear
              </button>
            )}
          </div>

          {notesLoading && (
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <RefreshCw className="h-3 w-3 animate-spin" aria-hidden="true" />
              Loading notes…
            </div>
          )}

          {!notesLoading && loadError && (
            <div
              className="flex items-center justify-between gap-2 rounded-lg border border-red-500/40 bg-red-900/20 p-2.5"
              data-testid="load-error"
            >
              <p className="text-xs text-red-300">Could not load notes: {loadError}</p>
              <button
                type="button"
                onClick={loadNotes}
                className="rounded-md border border-red-400/50 px-2 py-1 text-xs font-medium text-red-200 hover:bg-red-800/30 focus:outline-none focus:ring-2 focus:ring-red-400"
              >
                Retry
              </button>
            </div>
          )}

          {!notesLoading && !loadError && notes.length === 0 && (
            <p className="text-xs text-slate-500">No notes found. Capture some notes first.</p>
          )}

          {!notesLoading && !loadError && notes.length > 0 && (
            <div className="flex max-h-60 flex-col gap-1.5 overflow-y-auto pr-1">
              {notes.map((note) => {
                const isSelected = selectedIds.has(note.id);
                const snippet = (note.content || '').slice(0, 80);
                return (
                  <button
                    key={note.id}
                    type="button"
                    onClick={() => toggleNote(note.id)}
                    aria-pressed={isSelected}
                    className={[
                      'flex items-start gap-2 rounded-lg border p-2.5 text-left text-xs transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-400',
                      isSelected
                        ? 'border-indigo-500 bg-indigo-900/30 text-slate-200'
                        : 'border-slate-700 bg-slate-800/40 text-slate-400 hover:border-slate-600',
                    ].join(' ')}
                  >
                    <span
                      className={[
                        'mt-0.5 h-3 w-3 shrink-0 rounded-sm border',
                        isSelected
                          ? 'border-indigo-400 bg-indigo-400'
                          : 'border-slate-600 bg-transparent',
                      ].join(' ')}
                      aria-hidden="true"
                    />
                    <span className="flex-1">
                      <span className="font-medium text-slate-300">[{note.category}]</span>{' '}
                      {snippet}
                      {note.content.length > 80 ? '…' : ''}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </section>

        {validationError && (
          <p className="text-xs text-red-400" data-testid="validation-error">
            {validationError}
          </p>
        )}
        {generateError && (
          <p className="text-xs text-red-400" data-testid="generate-error">
            {generateError}
          </p>
        )}

        {/* Generate button */}
        <button
          ref={generateBtnRef}
          type="button"
          onClick={() => void handleGenerate()}
          disabled={isGenerating || selectedIds.size === 0}
          className="flex items-center justify-center gap-2 rounded-xl bg-indigo-600 py-3 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isGenerating ? (
            <>
              <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
              Generating…
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4" aria-hidden="true" />
              Generate {config.label}
            </>
          )}
        </button>

        {/* Generated output */}
        {generatedText && (
          <section className="rounded-xl border border-indigo-500/50 bg-indigo-900/20 p-4">
            <div className="mb-2 flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-indigo-400" aria-hidden="true" />
              <span className="text-xs font-semibold uppercase tracking-wide text-indigo-300">
                Generated {config.label}
              </span>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
              {generatedText}
            </p>

            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void handleCopy()}
                className="flex items-center gap-1 rounded-md border border-slate-600 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-400"
              >
                <CopyIcon className="h-3 w-3" aria-hidden="true" />
                Copy
              </button>
              <button
                type="button"
                onClick={() => void handleGenerate()}
                disabled={isGenerating}
                className="flex items-center gap-1 rounded-md border border-slate-600 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <RefreshCw
                  className={`h-3 w-3 ${isGenerating ? 'animate-spin' : ''}`}
                  aria-hidden="true"
                />
                Regenerate
              </button>
              <button
                type="button"
                onClick={() => void handleSaveAsNote()}
                disabled={isSaving}
                className="flex items-center gap-1 rounded-md border border-indigo-500 bg-indigo-600/20 px-2.5 py-1.5 text-xs font-medium text-indigo-200 hover:bg-indigo-600/40 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <SaveIcon className="h-3 w-3" aria-hidden="true" />
                Save as Note
              </button>
            </div>
            <div className="mt-2 min-h-[1rem] text-xs">
              {copyFlash && <span className="text-emerald-300">Copied!</span>}
              {savedFlash && <span className="text-emerald-300">Saved to Library!</span>}
              {saveError && (
                <span className="text-red-300" data-testid="save-error">
                  {saveError}
                </span>
              )}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
