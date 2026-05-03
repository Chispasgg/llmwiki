'use client'

import { useEffect } from 'react'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import { usePathname, useRouter } from 'next/navigation'
import { useUserStore } from '@/stores'

const NAV_LINKS = [
  { href: '/admin', label: 'Resumen' },
  { href: '/admin/users', label: 'Usuarios' },
  { href: '/admin/tokens', label: 'Tokens' },
  { href: '/admin/wikis', label: 'Wikis' },
  { href: '/admin/shares', label: 'Compartidas' },
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
      <nav className="border-b px-6 py-3 flex items-center gap-6 text-sm font-medium">
        <Link
          href="/wikis"
          className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground mr-2"
        >
          <ArrowLeft className="size-3.5" />
          Wikis
        </Link>
        <span className="text-border select-none">|</span>
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
