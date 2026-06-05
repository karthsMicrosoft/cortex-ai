import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import type { LocalNote } from '../db';
import { ProcessingBadge } from './ProcessingBadge';
import { CATEGORY_COLORS, formatDate, formatRelativeTime } from '../utils/formatters';

// ---------------------------------------------------------------------------
// Extended LocalNote with B8 AI-suggested fields
// ---------------------------------------------------------------------------

export interface LocalNoteWithAI extends LocalNote {
  /** Field names whose current value was populated by AI (not yet overridden by user) */
  aiSuggestedFields?: string[];
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface NoteCardProps {
  note: LocalNoteWithAI;
  children?: ReactNode;
  /** Optional override for tap behavior (e.g. in tests); if not provided, navigates */
  onPress?: (localId: string) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * NoteCard — renders a single note in the timeline feed.
 *
 * Displays:
 *  - Content snippet (first 200 chars)
 *  - Category chip (colour from CATEGORY_COLORS) + AI-suggested badge (B8)
 *  - Processing status badge (mitigation #5)
 *  - Relative creation date
 *  - Tags
 *
 * Tapping opens the detail page (/note/:localId) or calls onPress if provided.
 */
export function NoteCard({ note, children, onPress }: NoteCardProps): React.ReactElement {
  const navigate = useNavigate();
  const colors = CATEGORY_COLORS[note.category];
  const isAISuggestedCategory = note.aiSuggestedFields?.includes('category');

  const snippet =
    note.content.length > 200 ? `${note.content.slice(0, 200)}…` : note.content || '(recording…)';

  const dateLabel = `${formatDate(note.createdAt.toISOString())} · ${formatRelativeTime(note.createdAt.toISOString())}`;

  const handleClick = () => {
    if (onPress) {
      onPress(note.localId);
    } else {
      navigate(`/note/${note.localId}`);
    }
  };

  return (
    <article
      className="cursor-pointer rounded-xl border border-slate-700 bg-slate-800/60 p-4 transition-colors hover:border-indigo-500/60 hover:bg-slate-800"
      onClick={handleClick}
      tabIndex={0}
      aria-label={`Note: ${snippet}`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') handleClick();
      }}
    >
      {/* Header row */}
      <div className="mb-2 flex items-center justify-between gap-2">
        {/* Category chip */}
        <div className="flex items-center gap-1">
          <span
            className={[
              'rounded-full border px-2 py-0.5 text-xs font-semibold',
              colors.bg,
              colors.text,
              colors.border,
            ].join(' ')}
          >
            {note.category}
          </span>
          {isAISuggestedCategory && (
            <span className="inline-flex items-center rounded-full bg-indigo-900/60 px-1.5 py-0.5 text-[10px] font-medium text-indigo-300 border border-indigo-700">
              AI suggested
            </span>
          )}
        </div>

        {/* Date */}
        <time
          dateTime={note.createdAt.toISOString()}
          className="text-xs text-slate-400"
        >
          {dateLabel}
        </time>
      </div>

      {/* Content snippet */}
      <p
        className={[
          'text-sm leading-relaxed text-slate-200',
          children ? 'mb-0' : 'mb-3',
          note.done_at ? 'line-through' : '',
        ].join(' ')}
      >
        {snippet}
      </p>

      {children ? <div className="mb-3 mt-2 flex flex-wrap items-center gap-2">{children}</div> : null}

      {/* Footer row */}
      <div className="flex items-center justify-between gap-2">
        {/* Tags */}
        {note.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {note.tags.slice(0, 4).map((tag) => (
              <span
                key={tag}
                className="rounded-full bg-slate-700 px-2 py-0.5 text-xs text-slate-300"
              >
                {tag}
              </span>
            ))}
            {note.tags.length > 4 && (
              <span className="rounded-full bg-slate-700 px-2 py-0.5 text-xs text-slate-400">
                +{note.tags.length - 4}
              </span>
            )}
          </div>
        )}

        {/* Processing badge */}
        <div className="ml-auto">
          <ProcessingBadge status={note.processingStatus} />
        </div>
      </div>

      {/* Pending sync indicator */}
      {note.syncStatus === 'pending' && (
        <div className="mt-2 text-xs text-amber-400">Pending sync…</div>
      )}
      {note.syncStatus === 'conflict' && (
        <div className="mt-2 text-xs text-red-400">Sync conflict</div>
      )}
    </article>
  );
}

export default NoteCard;
