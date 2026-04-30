import { useCallback, useState } from 'react';
import { useLiveQuery } from 'dexie-react-hooks';
import { ArrowLeft, GitMerge } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { db } from '../db';
import type { LocalNote } from '../db';
import { updateNote } from '../api/notes';
import type { NoteOut } from '../api/notes';
import { NoteEditor } from '../components/NoteEditor';
import { formatDateTime } from '../utils/formatters';

// ---------------------------------------------------------------------------
// ConflictRow
// ---------------------------------------------------------------------------

interface ConflictRowProps {
  note: LocalNote;
  onResolved: () => void;
}

function ConflictRow({ note, onResolved }: ConflictRowProps): React.ReactElement {
  const [merging, setMerging] = useState(false);
  const [isWorking, setIsWorking] = useState(false);

  const serverVersion = note.conflictServerVersion as NoteOut | undefined;

  // ---------------------------------------------------------- Keep Local

  const handleKeepLocal = useCallback(async () => {
    if (!note.serverId) return;
    setIsWorking(true);
    try {
      await updateNote(note.serverId, { content: note.content });
      await db.notes.update(note.localId, {
        syncStatus: 'synced',
        conflictServerVersion: undefined,
        updatedAt: new Date(),
      });
      onResolved();
    } catch {
      // Stay in conflict state on error
    } finally {
      setIsWorking(false);
    }
  }, [note, onResolved]);

  // ---------------------------------------------------------- Keep Server

  const handleKeepServer = useCallback(async () => {
    if (!serverVersion) return;
    setIsWorking(true);
    try {
      await db.notes.update(note.localId, {
        content: serverVersion.content,
        category: serverVersion.category,
        tags: serverVersion.tags ?? [],
        mood: serverVersion.mood,
        processingStatus: serverVersion.processing_status as LocalNote['processingStatus'],
        syncStatus: 'synced',
        conflictServerVersion: undefined,
        updatedAt: new Date(),
      });
      onResolved();
    } catch {
      // Stay in conflict state on error
    } finally {
      setIsWorking(false);
    }
  }, [note, serverVersion, onResolved]);

  // ---------------------------------------------------------- Merge (open editor)

  const handleMergeEditorSave = useCallback(
    async (updated: NoteOut) => {
      await db.notes.update(note.localId, {
        content: updated.content,
        category: updated.category,
        tags: updated.tags ?? [],
        mood: updated.mood,
        syncStatus: 'synced',
        conflictServerVersion: undefined,
        updatedAt: new Date(),
      });
      setMerging(false);
      onResolved();
    },
    [note, onResolved],
  );

  return (
    <div className="rounded-xl border border-red-700/50 bg-slate-800/60 p-4">
      {/* Title */}
      <div className="mb-3 flex items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-red-400">
          Conflict
        </span>
        {note.serverId && (
          <span className="text-xs text-slate-500">
            Server ID: {note.serverId.slice(0, 8)}…
          </span>
        )}
      </div>

      {/* Side-by-side comparison */}
      <div className="mb-4 grid grid-cols-2 gap-3">
        {/* Local */}
        <div className="rounded-lg border border-indigo-700/40 bg-slate-900/60 p-3">
          <p className="mb-1 text-xs font-semibold text-indigo-400">Local (your edits)</p>
          <p className="mb-1 text-xs text-slate-500">
            {formatDateTime(note.updatedAt.toISOString())}
          </p>
          <p className="line-clamp-4 text-sm text-slate-300">{note.content || '(empty)'}</p>
        </div>

        {/* Server */}
        <div className="rounded-lg border border-amber-700/40 bg-slate-900/60 p-3">
          <p className="mb-1 text-xs font-semibold text-amber-400">Server (remote)</p>
          {serverVersion ? (
            <>
              <p className="mb-1 text-xs text-slate-500">
                {formatDateTime(serverVersion.updated_at)}
              </p>
              <p className="line-clamp-4 text-sm text-slate-300">
                {serverVersion.content || '(empty)'}
              </p>
            </>
          ) : (
            <p className="text-xs text-slate-500">(no server data)</p>
          )}
        </div>
      </div>

      {/* Merge editor */}
      {merging && serverVersion && (
        <div className="mb-4">
          <NoteEditor
            note={
              {
                ...serverVersion,
                content: note.content, // prefill with local content
              } as NoteOut
            }
            onSave={async (_patch) => { void handleMergeEditorSave(serverVersion as NoteOut); }}
            onCancel={() => { /* no-op: dialog stays open via outer cancel button */ }}
          />
        </div>
      )}

      {/* Actions */}
      {!merging && (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={isWorking}
            onClick={() => void handleKeepLocal()}
            className="rounded-lg border border-indigo-600 px-3 py-1.5 text-xs font-semibold text-indigo-300 transition-colors hover:bg-indigo-900/40 focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:opacity-50"
          >
            Keep Mine
          </button>
          <button
            type="button"
            disabled={isWorking || !serverVersion}
            onClick={() => void handleKeepServer()}
            className="rounded-lg border border-amber-600 px-3 py-1.5 text-xs font-semibold text-amber-300 transition-colors hover:bg-amber-900/40 focus:outline-none focus:ring-2 focus:ring-amber-400 disabled:opacity-50"
          >
            Keep Server
          </button>
          {serverVersion && (
            <button
              type="button"
              disabled={isWorking}
              onClick={() => setMerging(true)}
              className="flex items-center gap-1 rounded-lg border border-slate-600 px-3 py-1.5 text-xs font-semibold text-slate-300 transition-colors hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
            >
              <GitMerge className="h-3.5 w-3.5" aria-hidden="true" />
              Merge
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ConflictsPage
// ---------------------------------------------------------------------------

/**
 * ConflictsPage (B13) — lists notes where syncStatus='conflict'.
 *
 * Each row shows Local vs Server side-by-side with "Keep Mine / Keep Server / Merge".
 */
export default function ConflictsPage(): React.ReactElement {
  const navigate = useNavigate();
  const [resolvedIds, setResolvedIds] = useState<Set<string>>(new Set());

  const conflictNotes = useLiveQuery(
    () => db.notes.where('syncStatus').equals('conflict').toArray(),
    [],
    [] as LocalNote[],
  );

  const visible = (conflictNotes ?? []).filter((n) => !resolvedIds.has(n.localId));

  const handleResolved = useCallback((localId: string) => {
    setResolvedIds((prev) => new Set([...prev, localId]));
  }, []);

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
        <h1 className="text-lg font-semibold text-slate-100">
          Sync Conflicts
          {visible.length > 0 && (
            <span className="ml-2 rounded-full bg-red-700 px-2 py-0.5 text-xs text-white">
              {visible.length}
            </span>
          )}
        </h1>
      </header>

      <main className="flex flex-1 flex-col gap-4 px-4 py-5">
        {visible.length === 0 ? (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-sm text-slate-500">No conflicts — all synced and up to date!</p>
          </div>
        ) : (
          visible.map((note) => (
            <ConflictRow
              key={note.localId}
              note={note}
              onResolved={() => handleResolved(note.localId)}
            />
          ))
        )}
      </main>
    </div>
  );
}
