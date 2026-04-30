import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart2, Brain, Lightbulb, RefreshCw } from 'lucide-react';
import { apiGet } from '../api/client';

// ---------------------------------------------------------------------------
// Types (mirrors backend schemas)
// ---------------------------------------------------------------------------

interface DailySummary {
  id: string;
  summary_date: string;
  summary_text: string;
  key_themes: string[];
  note_count: number;
  mood_summary?: string;
  created_at: string;
}

interface WeeklySummary {
  week: string;
  summary_text: string;
  daily_summaries: Array<{ date: string; summary_text: string; note_count: number }>;
  note_count: number;
}

interface PatternItem {
  theme: string;
  evidence_note_ids: string[];
}

interface PatternsResponse {
  patterns: PatternItem[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function currentISOWeek(): string {
  const now = new Date();
  const jan4 = new Date(now.getFullYear(), 0, 4);
  const dayOfYear = Math.floor((now.getTime() - new Date(now.getFullYear(), 0, 0).getTime()) / 86400000);
  const weekNum = Math.ceil((dayOfYear + jan4.getDay()) / 7);
  return `${now.getFullYear()}-W${String(weekNum).padStart(2, '0')}`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface SummaryCardProps {
  title: string;
  icon: React.ReactElement;
  text: string | null;
  themes?: string[];
  noteCount?: number;
  isLoading: boolean;
  error: string | null;
}

function SummaryCard({
  title,
  icon,
  text,
  themes,
  noteCount,
  isLoading,
  error,
}: SummaryCardProps): React.ReactElement {
  if (isLoading) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-4">
        <div className="mb-3 flex items-center gap-2 text-slate-300">
          {icon}
          <span className="text-sm font-semibold">{title}</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <RefreshCw className="h-3 w-3 animate-spin" aria-hidden="true" />
          Loading…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-4">
        <div className="mb-3 flex items-center gap-2 text-slate-300">
          {icon}
          <span className="text-sm font-semibold">{title}</span>
        </div>
        <p className="text-xs text-slate-500">{error}</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-slate-300">
          {icon}
          <span className="text-sm font-semibold">{title}</span>
        </div>
        {noteCount !== undefined && (
          <span className="rounded-full bg-slate-700 px-2 py-0.5 text-xs text-slate-400">
            {noteCount} notes
          </span>
        )}
      </div>
      {text ? (
        <p className="text-sm leading-relaxed text-slate-200">{text}</p>
      ) : (
        <p className="text-xs text-slate-500">No summary available yet.</p>
      )}
      {themes && themes.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {themes.map((t) => (
            <span
              key={t}
              className="rounded-full bg-indigo-900/50 px-2 py-0.5 text-xs text-indigo-300"
            >
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// InsightsPage
// ---------------------------------------------------------------------------

/**
 * InsightsPage — daily/weekly summaries + AI-detected patterns.
 * US-6 Task 5.1.
 */
export default function InsightsPage(): React.ReactElement {
  const navigate = useNavigate();

  // Daily summary
  const [daily, setDaily] = useState<DailySummary | null>(null);
  const [dailyLoading, setDailyLoading] = useState(true);
  const [dailyError, setDailyError] = useState<string | null>(null);

  // Weekly summary
  const [weekly, setWeekly] = useState<WeeklySummary | null>(null);
  const [weeklyLoading, setWeeklyLoading] = useState(true);
  const [weeklyError, setWeeklyError] = useState<string | null>(null);

  // Patterns
  const [patterns, setPatterns] = useState<PatternItem[]>([]);
  const [patternsLoading, setPatternsLoading] = useState(true);
  const [patternsError, setPatternsError] = useState<string | null>(null);

  useEffect(() => {
    // Daily
    void apiGet<DailySummary>(`/api/ai/summary/daily?date=${todayISO()}`)
      .then((data) => setDaily(data))
      .catch((err: Error) => {
        // 404 means no summary yet for today — not a real error
        if ('status' in err && (err as { status: number }).status === 404) {
          setDailyError('No summary for today yet. It generates nightly.');
        } else {
          setDailyError(err.message);
        }
      })
      .finally(() => setDailyLoading(false));

    // Weekly
    void apiGet<WeeklySummary>(`/api/ai/summary/weekly?week=${currentISOWeek()}`)
      .then((data) => setWeekly(data))
      .catch((err: Error) => setWeeklyError(err.message))
      .finally(() => setWeeklyLoading(false));

    // Patterns
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
        {/* Daily Summary */}
        <SummaryCard
          title="Today's Summary"
          icon={<BarChart2 className="h-4 w-4 text-indigo-400" aria-hidden="true" />}
          text={daily?.summary_text ?? null}
          themes={daily?.key_themes}
          noteCount={daily?.note_count}
          isLoading={dailyLoading}
          error={dailyError}
        />

        {/* Weekly Summary */}
        <SummaryCard
          title="This Week"
          icon={<BarChart2 className="h-4 w-4 text-purple-400" aria-hidden="true" />}
          text={weekly?.summary_text ?? null}
          noteCount={weekly?.note_count}
          isLoading={weeklyLoading}
          error={weeklyError}
        />

        {/* Patterns */}
        <section className="rounded-xl border border-slate-700 bg-slate-800/60 p-4">
          <div className="mb-3 flex items-center gap-2 text-slate-300">
            <Lightbulb className="h-4 w-4 text-amber-400" aria-hidden="true" />
            <span className="text-sm font-semibold">Recurring Patterns</span>
          </div>

          {patternsLoading && (
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <RefreshCw className="h-3 w-3 animate-spin" aria-hidden="true" />
              Detecting patterns…
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
