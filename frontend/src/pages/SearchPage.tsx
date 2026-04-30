import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SearchBar } from '../components/SearchBar';
import type { SearchResult } from '../api/search';
import { CATEGORY_COLORS, formatRelativeTime } from '../utils/formatters';

// ---------------------------------------------------------------------------
// SearchPage
// ---------------------------------------------------------------------------

/**
 * SearchPage — natural-language search via POST /api/search.
 *
 * Uses SearchBar (debounced) + renders ranked results.
 */
export function SearchPage(): React.ReactElement {
  const navigate = useNavigate();
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const handleResults = (r: SearchResult[]) => {
    setResults(r);
    setHasSearched(true);
  };

  return (
    <div className="flex min-h-screen flex-col bg-[#0F172A] pb-24">
      {/* Header */}
      <header className="border-b border-slate-700 px-4 py-3">
        <h1 className="mb-3 text-lg font-semibold text-slate-100">Search</h1>
        <SearchBar onResults={handleResults} onLoading={setIsLoading} />
      </header>

      {/* Results */}
      <main className="flex flex-1 flex-col px-4 py-4">
        {isLoading && (
          <div className="flex justify-center py-8">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent" />
          </div>
        )}

        {!isLoading && !hasSearched && (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-sm text-slate-500">
              Search your notes with natural language. Type a query above to find notes.
            </p>
          </div>
        )}

        {!isLoading && hasSearched && results.length === 0 && (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-sm text-slate-500">No results found. Try a different query.</p>
          </div>
        )}

        {!isLoading && results.length > 0 && (
          <ul className="flex flex-col gap-3" role="list">
            {results.map((result) => {
              const colors = CATEGORY_COLORS[result.category];
              const snippet =
                result.content.length > 200
                  ? `${result.content.slice(0, 200)}…`
                  : result.content;

              return (
                <li
                  key={result.id}
                  className="cursor-pointer rounded-xl border border-slate-700 bg-slate-800/60 p-4 transition-colors hover:border-indigo-500/60 hover:bg-slate-800"
                  onClick={() => navigate(`/note/${result.id}`)}
                  role="listitem"
                  tabIndex={0}
                  aria-label={`Note: ${snippet}`}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') navigate(`/note/${result.id}`);
                  }}
                >
                  {/* Header */}
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span
                      className={[
                        'rounded-full border px-2 py-0.5 text-xs font-semibold',
                        colors.bg,
                        colors.text,
                        colors.border,
                      ].join(' ')}
                    >
                      {result.category}
                    </span>
                    <time
                      dateTime={result.created_at}
                      className="text-xs text-slate-400"
                    >
                      {formatRelativeTime(result.created_at)}
                    </time>
                  </div>

                  {/* Snippet */}
                  <p className="mb-2 text-sm leading-relaxed text-slate-200">{snippet}</p>

                  {/* Relevance score */}
                  <div className="flex items-center gap-3 text-xs text-slate-500">
                    <span>Relevance: {(result.combined_score * 100).toFixed(0)}%</span>
                    {result.summary && (
                      <span className="truncate text-slate-400 italic">{result.summary}</span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </main>
    </div>
  );
}

export default SearchPage;
