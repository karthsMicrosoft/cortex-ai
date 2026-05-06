import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Brain, Lightbulb, RefreshCw } from 'lucide-react';
import { apiGet } from '../api/client';

// ---------------------------------------------------------------------------
// Types (mirrors backend schemas)
//
// 2026-05-06: Daily/weekly summary cards removed entirely. The cron that
// generated those summaries was dropped per a user product decision (see
// DECISIONS.md S 22y, KNOWN_ISSUES.md, alembic migration 007). The Insights
// page now shows only AI-detected recurring patterns.
// ---------------------------------------------------------------------------

interface PatternItem {
  theme: string;
  evidence_note_ids: string[];
}

interface PatternsResponse {
  patterns: PatternItem[];
}

// ---------------------------------------------------------------------------
// InsightsPage
// ---------------------------------------------------------------------------

/**
 * InsightsPage - AI-detected recurring patterns across the last 14 days.
 * US-6 Task 5.1.
 */
export default function InsightsPage(): React.ReactElement {
  const navigate = useNavigate();

  const [patterns, setPatterns] = useState<PatternItem[]>([]);
  const [patternsLoading, setPatternsLoading] = useState(true);
  const [patternsError, setPatternsError] = useState<string | null>(null);

  useEffect(() => {
    void apiGet<PatternsResponse>('/api/insights/patterns')
      .then((data) => setPatterns(data.patterns))
      .catch((err: Error) => setPatternsError(err.message))
      .finally(() => setPatternsLoading(false));
  }, []);

  return (
    <div className="flex min-h-screen flex-col bg-[#0F172A] pb-24">
      {/* Header */}
      <header className="border-b border-slate-700 px-4 py-3">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold text-slate-100">Insights</h1>
          <button
            type="button"
            onClick={() => navigate('/brain')}
            className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:border-indigo-500 hover:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            aria-label="Open Brain View"
          >
            <Brain className="h-3.5 w-3.5" aria-hidden="true" />
            Brain View
          </button>
        </div>
      </header>

      <main className="flex flex-1 flex-col gap-4 px-4 py-4">
        {/* Patterns */}
        <section className="rounded-xl border border-slate-700 bg-slate-800/60 p-4">
          <div className="mb-3 flex items-center gap-2 text-slate-300">
            <Lightbulb className="h-4 w-4 text-amber-400" aria-hidden="true" />
            <span className="text-sm font-semibold">Recurring Patterns</span>
          </div>

          {patternsLoading && (
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <RefreshCw className="h-3 w-3 animate-spin" aria-hidden="true" />
              Detecting patterns...
            </div>
          )}

          {!patternsLoading && patternsError && (
            <p className="text-xs text-slate-500">{patternsError}</p>
          )}

          {!patternsLoading && !patternsError && patterns.length === 0 && (
            <p className="text-xs text-slate-500">
              No patterns detected yet. Add more notes over the next 14 days.
            </p>
          )}

          {!patternsLoading && patterns.length > 0 && (
            <ul className="flex flex-col gap-2">
              {patterns.map((p) => (
                <li
                  key={p.theme}
                  className="rounded-lg border border-slate-700 bg-slate-900/40 px-3 py-2"
                >
                  <p className="text-sm font-medium text-slate-200">{p.theme}</p>
                  {p.evidence_note_ids.length > 0 && (
                    <p className="mt-0.5 text-xs text-slate-500">
                      {p.evidence_note_ids.length} supporting note
                      {p.evidence_note_ids.length !== 1 ? 's' : ''}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}
