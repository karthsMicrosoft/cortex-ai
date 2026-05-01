import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Music, Pencil, Check, X, Trash2 } from 'lucide-react';
import { db } from '../db';
import type { LocalNote } from '../db';
import { deleteNote, getNote, updateNote } from '../api/notes';
import type { NoteOut } from '../api/notes';
import { searchSimilar } from '../api/search';
import type { SearchResult } from '../api/search';
import { NoteEditor } from '../components/NoteEditor';
import { ProcessingBadge } from '../components/ProcessingBadge';
import { MusicPlayer } from '../components/MusicPlayer';
import type { MusicMetadata } from '../components/MusicPlayer';
import { ShadowReaderPrompt } from '../components/ShadowReaderPrompt';
import { CATEGORY_COLORS, formatDateTime } from '../utils/formatters';

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
      const updated = await updateNote(noteId, {
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
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load note');
      } finally {
        setIsLoading(false);
      }
    })();
  }, [id]);

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
      const updated = await updateNote(targetServerId, patch);
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
          <NoteEditor
            note={serverNote}
            onSave={handleEditorSave}
            onCancel={handleEditorCancel}
          />
        ) : (
          <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-4">
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
              {localNote?.content || '(recording pending transcription…)'}
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
        {/* Shadow Reader prompt (US-8) — Bug 8 fix: persistent launcher button
            rendered for ALL synced notes; modal opens only on user click,
            regardless of status. */}
        {serverNote && (
          <section aria-label="Shadow Reader">
            <ShadowReaderPrompt
              noteId={serverNote.id}
              onComplete={() => {
                // Refresh note to pick up answered/dismissed status
                void getNote(serverNote.id).then(setServerNote).catch(() => undefined);
              }}
            />
          </section>
        )}
      </main>
    </div>
  );
}
