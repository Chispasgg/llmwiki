const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:1502'

export type AuthUser = {
  id: string
  email: string
  display_name: string
  role: 'admin' | 'editor' | 'viewer'
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const res = await fetch(`${API_URL}/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail?.code === 'invalid_credentials'
      ? 'Email o contraseña incorrectos'
      : 'Error al iniciar sesión')
  }
  return getMe() as Promise<AuthUser>
}

export async function logout(): Promise<void> {
  await fetch(`${API_URL}/v1/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  })
}

export async function getMe(): Promise<AuthUser | null> {
  const res = await fetch(`${API_URL}/v1/auth/me`, {
    credentials: 'include',
  })
  if (!res.ok) return null
  return res.json()
}
