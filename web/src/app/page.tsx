import { AuthRedirect } from './AuthRedirect'

// In hosted mode the middleware sends anonymous visitors to /login before they reach here.
// AuthRedirect handles already-authenticated users → /workspaces.
// The spinner is shown while the client hydrates and the redirect fires.
export default function HomePage() {
  return (
    <div className="flex min-h-svh items-center justify-center bg-background">
      <AuthRedirect />
      <div
        className="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-foreground"
        aria-label="Cargando"
      />
    </div>
  )
}
