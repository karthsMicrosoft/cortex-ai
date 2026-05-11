import { useMemo } from 'react';
import { X } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SearchFiltersValue {
  category?: string;
  tags?: string[];
  /** ISO date (YYYY-MM-DD) — lower bound on note created_at */
  since?: string;
  /** ISO date (YYYY-MM-DD) — upper bound on note created_at */
  until?: string;
}

interface SearchFiltersProps {
  value: SearchFiltersValue;
  onChange: (next: SearchFiltersValue) => void;
  /** Tag names available for selection. Empty list hides the section header. */
  availableTags?: string[];
}

const CATEGORIES = [
  'Music',
  'Fitness',
  'Journal',
  'Ideas',
  'Spiritual',
  'Learning',
] as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function hasAnyFilter(v: SearchFiltersValue): boolean {
  return Boolean(
    v.category ||
      (v.tags && v.tags.length > 0) ||
      v.since ||
      v.until,
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * SearchFilters — sidebar of filter controls (category dropdown, tag chips,
 * date range). All state is owned by the parent; this component is purely
 * controlled and emits the full next value via `onChange` on every change.
 */
export function SearchFilters({
  value,
  onChange,
  availableTags = [],
}: SearchFiltersProps): React.ReactElement {
  const tagsSet = useMemo(() => new Set(value.tags ?? []), [value.tags]);

  const update = (patch: Partial<SearchFiltersValue>) => {
    const next: SearchFiltersValue = { ...value, ...patch };
    // Drop empty fields so the URL/serialized form stays minimal
    (Object.keys(next) as (keyof SearchFiltersValue)[]).forEach((k) => {
      const v = next[k];
      if (v === undefined || v === '' || (Array.isArray(v) && v.length === 0)) {
        delete next[k];
      }
    });
    onChange(next);
  };

  const toggleTag = (tag: string) => {
    const current = value.tags ?? [];
    const next = current.includes(tag)
      ? current.filter((t) => t !== tag)
      : [...current, tag];
    update({ tags: next });
  };

  const visible = hasAnyFilter(value);

  return (
    <aside
      className="flex flex-col gap-5 rounded-xl border border-slate-700 bg-slate-800/40 p-4 text-slate-100"
      aria-label="Search filters"
    >
      {/* --- Category --- */}
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="search-filter-category"
          className="text-xs font-semibold uppercase tracking-wide text-slate-400"
        >
          Category
        </label>
        <select
          id="search-filter-category"
          value={value.category ?? ''}
          onChange={(e) =>
            update({ category: e.target.value === '' ? undefined : e.target.value })
          }
          className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        >
          <option value="">All</option>
          {CATEGORIES.map((cat) => (
            <option key={cat} value={cat}>
              {cat}
            </option>
          ))}
        </select>
      </div>

      {/* --- Tags --- */}
      {availableTags.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Tags
          </span>
          <div className="flex flex-wrap gap-2">
            {availableTags.map((tag) => {
              const selected = tagsSet.has(tag);
              return (
                <button
                  key={tag}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => toggleTag(tag)}
                  className={[
                    'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                    selected
                      ? 'border-indigo-500 bg-indigo-500/30 text-indigo-100'
                      : 'border-slate-600 bg-slate-900 text-slate-300 hover:border-indigo-500/60 hover:text-indigo-200',
                  ].join(' ')}
                >
                  {tag}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* --- Date range --- */}
      <div className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          Date range
        </span>
        <div className="flex flex-col gap-2">
          <label htmlFor="search-filter-since" className="flex items-center gap-2 text-xs text-slate-300">
            <span className="w-12">Since</span>
            <input
              id="search-filter-since"
              type="date"
              value={value.since ?? ''}
              onChange={(e) =>
                update({ since: e.target.value === '' ? undefined : e.target.value })
              }
              className="flex-1 rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </label>
          <label htmlFor="search-filter-until" className="flex items-center gap-2 text-xs text-slate-300">
            <span className="w-12">Until</span>
            <input
              id="search-filter-until"
              type="date"
              value={value.until ?? ''}
              onChange={(e) =>
                update({ until: e.target.value === '' ? undefined : e.target.value })
              }
              className="flex-1 rounded-lg border border-slate-600 bg-slate-900 px-2 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </label>
        </div>
      </div>

      {/* --- Clear --- */}
      {visible && (
        <button
          type="button"
          onClick={() => onChange({})}
          className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-xs font-medium text-slate-300 hover:border-rose-500/60 hover:text-rose-200"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
          Clear filters
        </button>
      )}
    </aside>
  );
}

export default SearchFilters;
