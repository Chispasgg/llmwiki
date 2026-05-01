'use client'

import Link from 'next/link'

export function SignupForm() {
  return (
    <div className="flex min-h-screen items-center justify-center p-8">
      <div className="w-full max-w-sm space-y-4 text-center">
        <h1 className="text-2xl font-bold">Registro cerrado</h1>
        <p className="text-sm text-muted-foreground">
          Las cuentas son creadas por el administrador.
        </p>
        <Link
          href="/login"
          className="inline-block text-sm font-medium underline text-foreground"
        >
          Iniciar sesión
        </Link>
      </div>
    </div>
  )
}
