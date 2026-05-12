/**
 * WikiContent — PR 6.5
 *
 * Renders a note's content with `[[Title]]` references converted to either:
 *   - clickable `<Link to="/note/<id>">` when the title resolves via the
 *     supplied `wikiLinks` map (keys must be lowercase titles or aliases),
 *   - or a span with title attribute "No matching note" when unresolved.
 *
 * The map should be built from the note's outgoing wiki links (see
 * NoteDetailPage where it's derived from `getNoteLinks(noteId)`).
 *
 * The base text styling is inherited from the parent — this component only
 * inserts inline elements.
 */
import { Link } from 'react-router-dom';
import React from 'react';

interface WikiTarget {
  id: string;
  title: string;
}

interface WikiContentProps {
  content: string;
  /** Map keyed by lowercased title/alias → resolved target. */
  wikiLinks: Map<string, WikiTarget>;
}

const WIKI_REF_RE = /\[\[([^\]\n]+)\]\]/g;

export function WikiContent({ content, wikiLinks }: WikiContentProps): React.ReactElement {
  if (!content) {
    return <></>;
  }

  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  // Reset state — RegExp with /g flag is stateful across calls.
  WIKI_REF_RE.lastIndex = 0;

  while ((match = WIKI_REF_RE.exec(content)) !== null) {
    const [full, inner] = match;
    const start = match.index;
    if (start > lastIndex) {
      parts.push(content.slice(lastIndex, start));
    }

    const ref = inner.trim();
    const target = wikiLinks.get(ref.toLowerCase());

    if (target) {
      parts.push(
        <Link
          key={`wiki-${start}`}
          to={`/note/${target.id}`}
          className="text-indigo-300 underline decoration-indigo-500/50 underline-offset-2 hover:text-indigo-200"
        >
          {ref}
        </Link>,
      );
    } else {
      parts.push(
        <span
          key={`wiki-${start}`}
          title="No matching note"
          className="text-slate-400 underline decoration-dotted decoration-slate-600 underline-offset-2"
        >
          {full}
        </span>,
      );
    }

    lastIndex = start + full.length;
  }

  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex));
  }

  return <>{parts}</>;
}
