'use client'

import * as React from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useUserStore, useKBStore } from '@/stores'
import { apiFetch } from '@/lib/api'

const isLocal = process.env.NEXT_PUBLIC_MODE === 'local'

interface AuthProviderProps {
  userId: string
  email: string
  children: React.ReactNode
}

export function AuthProvider({ userId, email, children }: AuthProviderProps) {
  const router = useRouter()
  const pathname = usePathname()
  const setUser = useUserStore((s) => s.setUser)
  const signOut = useUserStore((s) => s.signOut)
  const fetchKBs = useKBStore((s) => s.fetchKBs)
  const initialized = React.useRef(false)

  React.useEffect(() => {
    if (initialized.current) return
    initialized.current = true

    if (isLocal) {
      // Local mode: static session, no Supabase
      setUser({ id: userId, email, display_name: email.split('@')[0], role: 'admin' })
      fetchKBs()
      return
    }

    // Hosted mode: cookie-based session — fetch current user from API
    apiFetch<{ id: string; email: string; display_name: string; role: 'superadmin' | 'admin' | 'editor' | 'viewer' }>('/v1/me')
      .then((me) => {
        setUser({ id: me.id, email: me.email, display_name: me.display_name, role: me.role })
        fetchKBs()
      })
      .catch(() => {
        signOut()
        useKBStore.setState({ knowledgeBases: [], loading: false, error: null })
        router.replace('/login')
      })
  }, [userId, email, setUser, fetchKBs, router, pathname, signOut])

  return <>{children}</>
}
