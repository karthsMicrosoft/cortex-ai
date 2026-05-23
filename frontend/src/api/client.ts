import { useAuthStore } from '../store/authStore';

// ---------------------------------------------------------------------------
// Typed API error
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  code: string;
  detail: string;
  status: number;
  /** Seconds until the caller may retry. Populated for HTTP 429 responses
   * when the server returns a `Retry-After` header (slowapi sets this). */
  retryAfter?: number;

  constructor(status: number, code: string, detail: string, retryAfter?: number) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.detail = detail;
    if (retryAfter !== undefined) this.retryAfter = retryAfter;
  }
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown;
};

async function parseErrorBody(res: Response): Promise<{ code: string; detail: string }> {
  try {
    const json = await res.json();
    return {
      code: (json as Record<string, unknown>).code as string ?? 'unknown',
      detail: (json as Record<string, unknown>).detail as string ?? res.statusText,
    };
  } catch {
    return { code: 'unknown', detail: res.statusText };
  }
}

// API base URL — set via VITE_API_BASE_URL at build time. Falls back to relative
// (same-origin) URLs in dev where Vite's proxy handles the forwarding.
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

function resolveUrl(url: string): string {
  if (!API_BASE || /^https?:\/\//.test(url)) return url;
  return `${API_BASE}${url.startsWith('/') ? '' : '/'}${url}`;
}

/**
 * Resolve a relative API path against the configured API base. Use this for
 * raw fetch() calls (multipart uploads, FormData) that bypass apiPost helper.
 *
 * Example: apiUrl('/api/upload') -> 'https://cortexks-api.../api/upload'
 */
export function apiUrl(path: string): string {
  return resolveUrl(path);
}

/**
 * Build a WebSocket URL that targets the same host as the API base. Converts
 * https -> wss and http -> ws. Falls back to current page host in dev.
 *
 * Example: wsUrl('/api/voice/stream?token=abc')
 *   -> 'wss://cortexks-api.../api/voice/stream?token=abc'
 */
export function wsUrl(path: string): string {
  if (API_BASE) {
    return API_BASE.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:') +
      (path.startsWith('/') ? path : `/${path}`);
  }
  // Same-origin fallback (dev / SSR)
  const proto = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = typeof window !== 'undefined' ? window.location.host : 'localhost';
  return `${proto}//${host}${path.startsWith('/') ? path : `/${path}`}`;
}

async function fetchWithAuth(
  url: string,
  options: RequestOptions = {},
  _isRetry = false,
): Promise<Response> {
  const { accessToken } = useAuthStore.getState();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }

  const init: RequestInit = {
    ...options,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    credentials: 'include', // send/accept httpOnly refresh cookie cross-origin
  };

  const res = await fetch(resolveUrl(url), init);

  // On 401 — attempt token refresh once, then retry.
  // Guard: skip auto-refresh when the failing request IS the refresh endpoint
  // (avoids an infinite loop and prevents spurious logout on page reload when
  // the refresh cookie is still valid but the race hasn't resolved yet).
  const isRefreshEndpoint = resolveUrl(url).includes('/api/auth/refresh');
  if (res.status === 401 && !_isRetry && !isRefreshEndpoint) {
    try {
      // Round-7: include refresh_token from localStorage in the request body so
      // the backend can rotate even when Edge tracking-prevention blocks the
      // third-party httpOnly cookie.  credentials:'include' is kept so the
      // cookie path still works for browsers that honour SameSite=None+Secure.
      const storedRefresh = localStorage.getItem('cortex_refresh');
      const refreshBody = storedRefresh ? JSON.stringify({ refresh_token: storedRefresh }) : undefined;
      const refreshRes = await fetch(resolveUrl('/api/auth/refresh'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: refreshBody,
      });
      if (refreshRes.ok) {
        const data = (await refreshRes.json()) as { access_token: string; refresh_token?: string };
        if (data.refresh_token) {
          localStorage.setItem('cortex_refresh', data.refresh_token);
        }
        useAuthStore.getState().setAccessToken(data.access_token);
        // Retry the original request with the new token
        return fetchWithAuth(url, options, true);
      }
    } catch {
      // Refresh failed — clear auth state and fall through to throw
    }
    useAuthStore.getState().logout();
  }

  return res;
}

// ---------------------------------------------------------------------------
// Public API client
// ---------------------------------------------------------------------------

function parseRetryAfter(res: Response): number | undefined {
  if (res.status !== 429) return undefined;
  const raw = res.headers.get('Retry-After');
  if (!raw) return undefined;
  const n = Number(raw);
  if (Number.isFinite(n) && n >= 0) return n;
  // HTTP-date form — convert to seconds-from-now.
  const ts = Date.parse(raw);
  if (!Number.isNaN(ts)) {
    return Math.max(0, Math.round((ts - Date.now()) / 1000));
  }
  return undefined;
}

export async function apiGet<T>(url: string, options?: RequestOptions): Promise<T> {
  const res = await fetchWithAuth(url, { ...options, method: 'GET' });
  if (!res.ok) {
    const { code, detail } = await parseErrorBody(res);
    throw new ApiError(res.status, code, detail, parseRetryAfter(res));
  }
  return res.json() as Promise<T>;
}

export async function apiPost<T>(url: string, body?: unknown, options?: RequestOptions): Promise<T> {
  const res = await fetchWithAuth(url, { ...options, method: 'POST', body });
  if (!res.ok) {
    const { code, detail } = await parseErrorBody(res);
    throw new ApiError(res.status, code, detail, parseRetryAfter(res));
  }
  return res.json() as Promise<T>;
}

export async function apiPut<T>(url: string, body?: unknown, options?: RequestOptions): Promise<T> {
  const res = await fetchWithAuth(url, { ...options, method: 'PUT', body });
  if (!res.ok) {
    const { code, detail } = await parseErrorBody(res);
    throw new ApiError(res.status, code, detail, parseRetryAfter(res));
  }
  return res.json() as Promise<T>;
}

export async function apiPatch<T>(url: string, body?: unknown, options?: RequestOptions): Promise<T> {
  const res = await fetchWithAuth(url, { ...options, method: 'PATCH', body });
  if (!res.ok) {
    const { code, detail } = await parseErrorBody(res);
    throw new ApiError(res.status, code, detail, parseRetryAfter(res));
  }
  return res.json() as Promise<T>;
}

export async function apiDelete(url: string, options?: RequestOptions): Promise<void> {
  const res = await fetchWithAuth(url, { ...options, method: 'DELETE' });
  if (!res.ok) {
    const { code, detail } = await parseErrorBody(res);
    throw new ApiError(res.status, code, detail, parseRetryAfter(res));
  }
}
