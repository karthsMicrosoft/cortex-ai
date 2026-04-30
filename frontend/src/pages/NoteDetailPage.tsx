import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Music } from 'lucide-react';
import { db } from '../db';
import type { LocalNote } from '../db';
import { getNote } from '../api/notes';
import type { NoteOut } from '../api/notes';
import { searchSimilar } from '../api/search';
import type { SearchResult } from '../api/search';
import { NoteEditor } from '../components/NoteEditor';
import { ProcessingBadge } from '../components/ProcessingBadge';
import { CATEGORY_COLORS, formatDateTime } from '../utils/formatters';

// ---------------------------------------------------------------------------
// NoteDetailPage
// ---------------------------------------------------------------------------

/**
 * NoteDetailPage — full note view.
 *
 * - Shows ProcessingBadge, tags, category, timestamps
 * - Renders NoteEditor for manual overrides (B8)
 * - Audio player placeholder (real player lands in US-6 + US-9)
 * - Fetches related notes via /api/search/similar/{id}
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
        // Try IndexedDB first (offline-first)
        const local = await db.notes.get(id);
        if (local) setLocalNote(local);

        // If the note has a serverId, fetch from API
        const sId = local?.serverId ?? id;
        try {
          const server = await getNote(sId);
          setServerNote(server);
        } catch {
          // Offline or not yet synced — stay with local
        }

        // Fetch related notes (server only, optional)
        if (local?.serverId ?? id) {
          try {
            const rel = await searchSimilar(local?.serverId ?? id);
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
  const createdAt = serverNote?.created_at ?? localNote?.createdAt.toISOString() ?? '';
  const updatedAt = serverNote?.updated_at ?? localNote?.updatedAt.toISOString() ?? '';

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
      </header>

      <main className="flex flex-1 flex-col gap-5 px-4 py-5">
        {/* Timestamps */}
        <div className="flex gap-4 text-xs text-slate-500">
          <span>Created: {formatDateTime(createdAt)}</span>
          <span>Updated: {formatDateTime(updatedAt)}</span>
        </div>

        {/* Audio player placeholder */}
        {audioUrl && (
          <div className="flex items-center gap-3 rounded-xl border border-slate-700 bg-slate-800/60 p-4">
            <Music className="h-5 w-5 text-indigo-400" aria-hidden="true" />
            <div className="flex-1">
              <p className="text-xs text-slate-400">Audio recording</p>
              {/* Real waveform player lands in US-6 + US-9 */}
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
          <NoteEditor note={serverNote} onSaved={handleSaved} />
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
      </main>
    </div>
  );
}
