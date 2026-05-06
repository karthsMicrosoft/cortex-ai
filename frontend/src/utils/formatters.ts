import { format, formatDistanceToNow, parseISO } from 'date-fns';
import type { Category } from '../api/notes';

// ---------------------------------------------------------------------------
// Date formatters
// ---------------------------------------------------------------------------

/** Format an ISO date string to a human-readable absolute date, e.g. "Apr 29, 2026" */
export function formatDate(isoString: string): string {
  return format(parseISO(isoString), 'MMM d, yyyy');
}

/** Format an ISO date string to a relative time, e.g. "3 hours ago" */
export function formatRelativeTime(isoString: string): string {
  return formatDistanceToNow(parseISO(isoString), { addSuffix: true });
}

/** Format an ISO date string to a full timestamp, e.g. "Apr 29, 2026, 14:32" */
export function formatDateTime(isoString: string): string {
  return format(parseISO(isoString), 'MMM d, yyyy, HH:mm');
}

// ---------------------------------------------------------------------------
// Category color map (Tailwind class names)
// ---------------------------------------------------------------------------

export const CATEGORY_COLORS: Record<Category, { bg: string; text: string; border: string }> = {
  Music:      { bg: 'bg-purple-900/40', text: 'text-purple-300', border: 'border-purple-500' },
  Fitness:    { bg: 'bg-green-900/40',  text: 'text-green-300',  border: 'border-green-500'  },
  Journal:    { bg: 'bg-blue-900/40',   text: 'text-blue-300',   border: 'border-blue-500'   },
  Ideas:      { bg: 'bg-indigo-900/40', text: 'text-indigo-300', border: 'border-indigo-500' },
  Spiritual:  { bg: 'bg-amber-900/40',  text: 'text-amber-300',  border: 'border-amber-500'  },
  Learning:   { bg: 'bg-cyan-900/40',   text: 'text-cyan-300',   border: 'border-cyan-500'   },
};

// ---------------------------------------------------------------------------
// Word count helper
// ---------------------------------------------------------------------------

/**
 * Count the number of words in a string.
 * Splits on any whitespace; ignores empty tokens.
 */
export function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}
