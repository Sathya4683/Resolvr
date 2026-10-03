//tiny fetch wrapper: adds the token, turns error responses into exceptions with a readable message

export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8001'
const TOKEN_KEY = 'resolvr.token'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    //fastapi validation errors come back as a list
    if (Array.isArray(detail) && detail[0]?.msg) return `${detail[0].loc?.slice(-1)[0] ?? 'field'}: ${detail[0].msg}`
  }
  return fallback
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')

  const res = await fetch(`${API_URL}${path}`, { ...options, headers })
  if (res.status === 401 && token) onUnauthorized?.()
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, errorMessage(body, `Request failed (${res.status})`))
  }
  if (res.status === 204) return undefined as T
  const type = res.headers.get('content-type') ?? ''
  return (type.includes('application/json') ? res.json() : res.blob()) as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body ?? {}) }),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
}

export async function downloadFile(path: string, filename: string) {
  const blob = await request<Blob>(path)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

//report browser errors to the api so they end up in loki next to the backend logs
export function reportClientError(message: string, extra: Record<string, unknown> = {}) {
  fetch(`${API_URL}/v1/client-logs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ level: 'error', message: message.slice(0, 500), path: location.pathname, ...extra }),
  }).catch(() => {})
}
