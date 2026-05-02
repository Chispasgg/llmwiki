'use client'

import { useEffect, useState } from 'react'
import { listAllAPIKeys, revokeAnyAPIKey, type AdminAPIKey } from '@/lib/admin'

export default function AdminTokensPage() {
  const [keys, setKeys] = useState<AdminAPIKey[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    listAllAPIKeys()
      .then(setKeys)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleRevoke = async (key: AdminAPIKey) => {
    if (!confirm(`¿Revocar el token "${key.name ?? key.key_prefix}" de ${key.user_email}?`)) return
    try {
      await revokeAnyAPIKey(key.id)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (loading) return <p className="text-muted-foreground">Cargando...</p>

  return (
    <div>
      <h1 className="text-xl font-semibold mb-6">Tokens de acceso</h1>
      {error && <p className="text-destructive mb-4">{error}</p>}
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-2 pr-4">Usuario</th>
            <th className="py-2 pr-4">Nombre</th>
            <th className="py-2 pr-4">Prefijo</th>
            <th className="py-2 pr-4">Estado</th>
            <th className="py-2 pr-4">Creado</th>
            <th className="py-2 pr-4">Último uso</th>
            <th className="py-2">Acción</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => (
            <tr key={k.id} className="border-b hover:bg-muted/40">
              <td className="py-2 pr-4">{k.user_email}</td>
              <td className="py-2 pr-4">{k.name ?? '—'}</td>
              <td className="py-2 pr-4 font-mono text-xs">{k.key_prefix}…</td>
              <td className="py-2 pr-4">
                <span className={`text-xs px-2 py-0.5 rounded ${k.revoked_at ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>
                  {k.revoked_at ? 'Revocado' : 'Activo'}
                </span>
              </td>
              <td className="py-2 pr-4 text-muted-foreground">
                {new Date(k.created_at).toLocaleDateString('es')}
              </td>
              <td className="py-2 pr-4 text-muted-foreground">
                {k.last_used_at ? new Date(k.last_used_at).toLocaleString('es') : '—'}
              </td>
              <td className="py-2">
                {!k.revoked_at && (
                  <button
                    onClick={() => handleRevoke(k)}
                    className="text-xs text-destructive hover:underline"
                  >
                    Revocar
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
