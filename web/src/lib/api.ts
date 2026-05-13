export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:1502'
const WS_URL = API_URL.replace(/^http/, 'ws')
const isLocal = process.env.NEXT_PUBLIC_MODE === 'local'
export const API_CREDENTIALS: RequestCredentials = isLocal ? 'omit' : 'include'

export async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const headers: Record<string, string> = {
    ...(typeof options?.body === 'string'
      ? { 'Content-Type': 'application/json' }
      : {}),
    ...options?.headers as Record<string, string>,
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    credentials: isLocal ? 'omit' : 'include',
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `API error: ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export function getDocumentsWsUrl(kbId: string): string {
  return `${WS_URL}/v1/ws/documents/${kbId}`
}
