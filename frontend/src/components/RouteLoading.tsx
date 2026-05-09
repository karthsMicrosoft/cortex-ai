import type { ReactElement } from 'react';

/**
 * RouteLoading — Suspense fallback for lazy-loaded route chunks.
 *
 * PERF (Round 15 / PR #25): pages outside the auth + capture entry path are
 * code-split via `React.lazy()` so the initial JS bundle stays small. While
 * those chunks are downloading, this component fills the viewport with a
 * dark-slate spinner that matches the existing SessionGate splash, so the
 * transition between routes is visually consistent.
 *
 * Accessibility:
 *   - role="status" exposes the spinner as a polite live region.
 *   - aria-label="Loading page" gives screen-reader users a stable string
 *     even if the visible label is hidden.
 */
export interface RouteLoadingProps {
  /** Optional visible label. Defaults to "Loading...". */
  label?: string;
}

export function RouteLoading({ label = 'Loading...' }: RouteLoadingProps = {}): ReactElement {
  return (
    <div
      role="status"
      aria-label="Loading page"
      className="flex min-h-screen flex-col items-center justify-center gap-3 bg-[#0F172A]"
    >
      <div
        className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent"
        aria-hidden="true"
      />
      <span className="text-sm text-slate-400">{label}</span>
    </div>
  );
}

export default RouteLoading;
