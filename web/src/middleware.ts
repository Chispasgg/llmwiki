import { NextResponse, type NextRequest } from 'next/server'

const isLocal = process.env.NEXT_PUBLIC_MODE === 'local'
const PUBLIC_PATHS = ['/login', '/_next', '/favicon.ico']

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  if (isLocal) {
    if (pathname === '/') {
      return NextResponse.redirect(new URL('/wikis', request.url))
    }
    return NextResponse.next()
  }

  // Hosted: dejar pasar rutas públicas
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next()
  }

  // Verificar que la cookie de sesión existe
  const sessionCookie = request.cookies.get('wiki_session')
  if (!sessionCookie) {
    const loginUrl = new URL('/login', request.url)
    loginUrl.searchParams.set('next', pathname)
    return NextResponse.redirect(loginUrl)
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
}
