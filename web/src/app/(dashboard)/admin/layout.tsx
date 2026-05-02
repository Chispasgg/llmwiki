'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useUserStore } from '@/stores'

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const user = useUserStore((s) => s.user)
  const authLoading = useUserStore((s) => s.authLoading)
  const router = useRouter()

  useEffect(() => {
    if (!authLoading && user && user.role !== 'superadmin') {
      router.replace('/wikis')
    }
    if (!authLoading && !user) {
      router.replace('/login')
    }
  }, [user, authLoading, router])

  if (authLoading || !user || user.role !== 'superadmin') {
    return null
  }

  return (
    <div className="min-h-full">
      <nav className="border-b px-6 py-3 flex gap-6 text-sm font-medium">
        <a href="/admin" className="hover:text-foreground text-muted-foreground">Resumen</a>
        <a href="/admin/users" className="hover:text-foreground text-muted-foreground">Usuarios</a>
        <a href="/admin/tokens" className="hover:text-foreground text-muted-foreground">Tokens</a>
        <a href="/admin/wikis" className="hover:text-foreground text-muted-foreground">Wikis</a>
        <a href="/admin/logs" className="hover:text-foreground text-muted-foreground">Logs</a>
      </nav>
      <div className="p-6">{children}</div>
    </div>
  )
}
