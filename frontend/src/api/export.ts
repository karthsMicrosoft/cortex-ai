/**
 * api/export.ts — user-data export helper.
 *
 * Wraps GET /api/export (backend backend/app/api/export.py) and triggers a
 * browser download with a dated filename so users can take their data with
 * them at any time.  Auth header is attached manually using the current
 * access token from useAuthStore — fetchWithAuth in api/client.ts is private
 * and JSON-only, but this helper needs the raw blob for download.
 */
import { apiUrl } from './client';
import { useAuthStore } from '../store/authStore';

function todayStamp(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

/**
 * Fetch /api/export and trigger a browser download of the JSON payload.
 * Filename: `cortex-export-YYYY-MM-DD.json` (today's date, local time).
 *
 * Throws on non-2xx responses so the caller can render an error microcopy.
 */
export async function downloadExport(): Promise<void> {
  const { accessToken } = useAuthStore.getState();
  const headers: Record<string, string> = {};
  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }

  const res = await fetch(apiUrl('/api/export'), {
    method: 'GET',
    headers,
    credentials: 'include',
  });

  if (!res.ok) {
    throw new Error(`Export failed: ${res.status} ${res.statusText}`);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement('a');
    a.href = url;
    a.download = `cortex-export-${todayStamp()}.json`;
    // Some test environments don't auto-attach; appendChild before click
    // makes the click reliable in Firefox / older Safari too.
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
