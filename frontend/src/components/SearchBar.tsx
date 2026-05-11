import { useCallback, useEffect, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';
import { search } from '../api/search';
import type { SearchResult } from '../api/search';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface SearchBarFilters {
  category?: string;
  tags?: string[];
  /** ISO YYYY-MM-DD — mapped to backend `date_from` */
  since?: string;
  /** ISO YYYY-MM-DD — mapped to backend `date_to` */
  until?: string;
}

interface SearchBarProps {
  /** Called whenever results change (including empty array on clear) */
  onResults: (results: SearchResult[]) => void;
  /** Called when a search is in-flight */
  onLoading?: (loading: boolean) => void;
  /** Optional filters; when these change AND a query exists, search re-runs. */
  filters?: SearchBarFilters;
  /** Initial query value — useful for hydrating from URL params. */
  initialQuery?: string;
  /** Notified whenever the user edits the query (for URL sync). */
  onQueryChange?: (query: string) => void;
  placeholder?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const DEBOUNCE_MS = 300;

/**
 * SearchBar — debounced text input; calls POST /api/search and emits results
 * upward via onResults callback.
 */
export function SearchBar({
  onResults,
  onLoading,
  filters,
  initialQuery = '',
  onQueryChange,
  placeholder = 'Search notes…',
}: SearchBarProps): React.ReactElement {
  const [query, setQuery] = useState(initialQuery);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Stable serialized form of filters so the effect dep array can compare cheaply.
  const filtersKey = JSON.stringify(filters ?? {});

  const runSearch = useCallback(
    async (q: string) => {
      if (!q.trim()) {
        onResults([]);
        onLoading?.(false);
        return;
      }

      // Cancel previous in-flight request
      abortRef.current?.abort();
      abortRef.current = new AbortController();

      onLoading?.(true);
      try {
        const results = await search({
          query: q,
          limit: 20,
          category: filters?.category,
          tags: filters?.tags,
          date_from: filters?.since,
          date_to: filters?.until,
        });
        onResults(results);
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return;
        onResults([]);
      } finally {
        onLoading?.(false);
      }
    },
    [onResults, onLoading, filters?.category, filters?.tags, filters?.since, filters?.until],
  );

  // Debounce query changes AND react to filter changes
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void runSearch(query);
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // filtersKey ensures we re-debounce on filter change. runSearch already
    // depends on the filter primitives so the closure is fresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, runSearch, filtersKey]);

  const handleClear = useCallback(() => {
    setQuery('');
    onQueryChange?.('');
    onResults([]);
    onLoading?.(false);
  }, [onResults, onLoading, onQueryChange]);

  return (
    <div className="relative flex items-center">
      <Search
        className="pointer-events-none absolute left-3 h-4 w-4 text-slate-400"
        aria-hidden="true"
      />
      <input
        type="search"
        role="searchbox"
        aria-label="Search notes"
        className="w-full rounded-xl border border-slate-600 bg-slate-800 py-2.5 pl-9 pr-9 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        placeholder={placeholder}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          onQueryChange?.(e.target.value);
        }}
      />
      {query && (
        <button
          type="button"
          aria-label="Clear search"
          onClick={handleClear}
          className="absolute right-3 text-slate-400 hover:text-slate-200 focus:outline-none"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}

export default SearchBar;
