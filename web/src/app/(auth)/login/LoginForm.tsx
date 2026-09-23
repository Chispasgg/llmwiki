'use client'

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { login, getMe } from '@/lib/auth'
import { useUserStore } from '@/stores/useUserStore'
import { BrandLogo } from '@/components/brand/BrandLogo'
import { fetchBranding, type Branding } from '@/lib/branding'

export function LoginForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const setUser = useUserStore((s) => s.setUser)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [checking, setChecking] = useState(true)
  const [branding, setBranding] = useState<Branding | null>(null)

  // Fetch branding for the logo (fire-and-forget; fallback = chevron while loading)
  useEffect(() => {
    fetchBranding().then(setBranding)
  }, [])

  // Redirect immediately if session cookie is still valid
  useEffect(() => {
    getMe().then((me) => {
      if (me) {
        setUser(me)
        const rawNext = searchParams.get('next') || '/workspaces'
        const nextPath = rawNext.startsWith('/') && !rawNext.startsWith('//') ? rawNext : '/workspaces'
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
      const rawNext = searchParams.get('next') || '/workspaces'
      const nextPath = rawNext.startsWith('/') && !rawNext.startsWith('//') ? rawNext : '/workspaces'
      router.push(nextPath)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setLoading(false)
    }
  }

  if (checking) return null

  return (
    <div className="relative flex min-h-svh flex-col items-center justify-center bg-background px-4">
      {/* Warm halo — light theme (subtle amber) */}
      <div
        className="pointer-events-none absolute inset-0 -z-10 dark:hidden"
        style={{
          background:
            'radial-gradient(ellipse 80% 50% at 50% 35%, hsl(38 80% 70% / 0.12), transparent)',
        }}
        aria-hidden="true"
      />
      {/* Warm halo — dark theme (slightly more visible) */}
      <div
        className="pointer-events-none absolute inset-0 -z-10 hidden dark:block"
        style={{
          background:
            'radial-gradient(ellipse 80% 50% at 50% 35%, hsl(38 80% 60% / 0.22), transparent)',
        }}
        aria-hidden="true"
      />

      <div className="flex w-full max-w-sm flex-col items-center gap-8">
        {/* Brand section */}
        <div className="flex flex-col items-center gap-3">
          {/* Logo container with warm soft shadow */}
          <div className="flex items-center justify-center rounded-2xl border border-border/50 bg-card p-3 shadow-sm">
            <BrandLogo logo={branding?.logo ?? null} size={52} rounded />
          </div>

          {/* Wordmark + signature */}
          <div className="flex flex-col items-center gap-1">
            <span className="font-sans text-[clamp(27px,4vw,33px)] font-semibold tracking-tight text-foreground">
              LLM Wiki
            </span>
            <span className="font-mono text-[0.6875rem] uppercase tracking-[0.3em] text-muted-foreground">
              by <span className="text-accent-blue">PGG</span>
            </span>
          </div>
        </div>

        {/* Login form */}
        <form
          onSubmit={handleSubmit}
          className="flex w-full flex-col gap-5 rounded-xl border border-border bg-card p-8 shadow-sm"
        >
          {error && (
            <p role="alert" className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="login-email"
              className="font-mono text-[0.6875rem] uppercase tracking-wider text-muted-foreground"
            >
              Email
            </label>
            <input
              id="login-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="rounded-xl border border-input bg-background px-3 py-2 text-sm text-foreground outline-none transition placeholder:text-muted-foreground/50 focus:border-[hsl(var(--accent-blue))] focus:ring-2 focus:ring-[hsl(var(--accent-blue))]/20 disabled:opacity-50"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="login-password"
              className="font-mono text-[0.6875rem] uppercase tracking-wider text-muted-foreground"
            >
              Contraseña
            </label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="rounded-xl border border-input bg-background px-3 py-2 text-sm text-foreground outline-none transition placeholder:text-muted-foreground/50 focus:border-[hsl(var(--accent-blue))] focus:ring-2 focus:ring-[hsl(var(--accent-blue))]/20 disabled:opacity-50"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="mt-1 w-full rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? 'Entrando…' : 'Entrar'}
          </button>
        </form>
      </div>
    </div>
  )
}
