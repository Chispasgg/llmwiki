'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useUserStore } from '@/stores'

const NAV_LINKS = [
  { href: '/admin', label: 'Resumen' },
  { href: '/admin/users', label: 'Usuarios' },
  { href: '/admin/tokens', label: 'Tokens' },
  { href: '/admin/wikis', label: 'Wikis' },
  { href: '/admin/logs', label: 'Logs' },
]

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const user = useUserStore((s) => s.user)
  const authLoading = useUserStore((s) => s.authLoading)
  const router = useRouter()
  const pathname = usePathname()

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
        {NAV_LINKS.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className={pathname === href
              ? 'text-foreground'
              : 'text-muted-foreground hover:text-foreground'}
          >
            {label}
          </Link>
        ))}
      </nav>
      <div className="p-6">{children}</div>
    </div>
  )
}
