import { useCallback, useEffect, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';
import { search } from '../api/search';
import type { SearchResult } from '../api/search';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SearchBarProps {
  /** Called whenever results change (including empty array on clear) */
  onResults: (results: SearchResult[]) => void;
  /** Called when a search is in-flight */
  onLoading?: (loading: boolean) => void;
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
  placeholder = 'Search notes…',
}: SearchBarProps): React.ReactElement {
  const [query, setQuery] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

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
        const results = await search({ query: q, limit: 20 });
        onResults(results);
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return;
        onResults([]);
      } finally {
        onLoading?.(false);
      }
    },
    [onResults, onLoading],
  );

  // Debounce query changes
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void runSearch(query);
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, runSearch]);

  const handleClear = useCallback(() => {
    setQuery('');
    onResults([]);
    onLoading?.(false);
  }, [onResults, onLoading]);

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
        onChange={(e) => setQuery(e.target.value)}
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
