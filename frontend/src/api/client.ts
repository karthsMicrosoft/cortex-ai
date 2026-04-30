import { useAuthStore } from '../store/authStore';

// ---------------------------------------------------------------------------
// Typed API error
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  code: string;
  detail: string;
  status: number;

  constructor(status: number, code: string, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.detail = detail;
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
  };

  const res = await fetch(url, init);

  // On 401 — attempt token refresh once, then retry
  if (res.status === 401 && !_isRetry) {
    try {
      const refreshRes = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'include' });
      if (refreshRes.ok) {
        const data = (await refreshRes.json()) as { access_token: string };
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

export async function apiGet<T>(url: string, options?: RequestOptions): Promise<T> {
  const res = await fetchWithAuth(url, { ...options, method: 'GET' });
  if (!res.ok) {
    const { code, detail } = await parseErrorBody(res);
    throw new ApiError(res.status, code, detail);
  }
  return res.json() as Promise<T>;
}

export async function apiPost<T>(url: string, body?: unknown, options?: RequestOptions): Promise<T> {
  const res = await fetchWithAuth(url, { ...options, method: 'POST', body });
  if (!res.ok) {
    const { code, detail } = await parseErrorBody(res);
    throw new ApiError(res.status, code, detail);
  }
  return res.json() as Promise<T>;
}

export async function apiPut<T>(url: string, body?: unknown, options?: RequestOptions): Promise<T> {
  const res = await fetchWithAuth(url, { ...options, method: 'PUT', body });
  if (!res.ok) {
    const { code, detail } = await parseErrorBody(res);
    throw new ApiError(res.status, code, detail);
  }
  return res.json() as Promise<T>;
}

export async function apiDelete(url: string, options?: RequestOptions): Promise<void> {
  const res = await fetchWithAuth(url, { ...options, method: 'DELETE' });
  if (!res.ok) {
    const { code, detail } = await parseErrorBody(res);
    throw new ApiError(res.status, code, detail);
  }
}
