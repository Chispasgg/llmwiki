'use client'

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { login, getMe } from '@/lib/auth'
import { useUserStore } from '@/stores/useUserStore'

export function LoginForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const setUser = useUserStore((s) => s.setUser)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [checking, setChecking] = useState(true)

  // Redirect immediately if session cookie is still valid
  useEffect(() => {
    getMe().then((me) => {
      if (me) {
        setUser(me)
        const rawNext = searchParams.get('next') || '/wikis'
        const nextPath = rawNext.startsWith('/') && !rawNext.startsWith('//') ? rawNext : '/wikis'
        router.replace(nextPath)
      } else {
        setChecking(false)
      }
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const user = await login(email, password)
      setUser(user)
      const rawNext = searchParams.get('next') || '/wikis'
      const nextPath = rawNext.startsWith('/') && !rawNext.startsWith('//') ? rawNext : '/wikis'
      router.push(nextPath)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setLoading(false)
    }
  }

  if (checking) return null

  return (
    <main className="flex min-h-screen items-center justify-center bg-background">
      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-4 w-full max-w-sm p-8 border rounded-lg shadow-sm"
      >
        <h1 className="text-xl font-semibold">Iniciar sesión</h1>
        {error && (
          <p className="text-sm text-destructive">{error}</p>
        )}
        <label className="flex flex-col gap-1 text-sm">
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="border rounded px-3 py-2"
            autoComplete="email"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Contraseña
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="border rounded px-3 py-2"
            autoComplete="current-password"
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="bg-primary text-primary-foreground rounded py-2 font-medium disabled:opacity-50"
        >
          {loading ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </main>
  )
}
