import { AppShell } from '@/components/layout/AppShell'
import { AuthProvider } from '@/components/auth/AuthProvider'

const isLocal = process.env.NEXT_PUBLIC_MODE === 'local'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  // Local mode: static session. Hosted mode: AuthProvider validates cookie via /v1/me.
  const userId = isLocal ? 'local' : ''
  const email = isLocal ? 'local@localhost' : ''

  return (
    <AuthProvider userId={userId} email={email}>
      <AppShell>{children}</AppShell>
    </AuthProvider>
  )
}
