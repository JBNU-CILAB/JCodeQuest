import { supabase } from './supabase'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const { data: { session } } = await supabase.auth.getSession()
  return session?.access_token
    ? { Authorization: `Bearer ${session.access_token}` }
    : {}
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(await authHeader()),
      ...(init?.headers ?? {}),
    },
  })

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    if (res.status === 401) {
      await supabase.auth.signOut()
    }
    const detail = (body && typeof body === 'object' && 'detail' in body)
      ? String((body as { detail: unknown }).detail)
      : res.statusText
    throw new ApiError(res.status, body, `${init?.method ?? 'GET'} ${path} → ${res.status} ${detail}`)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const apiGet = <T>(path: string, init?: RequestInit) =>
  request<T>(path, { ...init, method: 'GET' })

export const apiPost = <T>(path: string, body?: unknown, init?: RequestInit) =>
  request<T>(path, {
    ...init,
    method: 'POST',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

export const apiPut = <T>(path: string, body?: unknown, init?: RequestInit) =>
  request<T>(path, {
    ...init,
    method: 'PUT',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

export interface SseHandlers<T> {
  onMessage: (data: T) => void
  onError?: (err: Event) => void
}

export function apiSse<T>(path: string, handlers: SseHandlers<T>): () => void {
  const es = new EventSource(`${API_BASE}${path}`)
  es.onmessage = (e) => {
    try {
      handlers.onMessage(JSON.parse(e.data) as T)
    } catch {
      // ignore non-JSON keep-alive frames
    }
  }
  if (handlers.onError) es.onerror = handlers.onError
  return () => es.close()
}
