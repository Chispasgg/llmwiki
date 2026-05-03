'use client'

import { useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import { listAllShares, deleteAnyShare, type AdminShare } from '@/lib/admin'

export default function AdminSharesPage() {
  const [shares, setShares] = useState<AdminShare[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listAllShares()
      .then(setShares)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  async function handleRevoke(share: AdminShare) {
    try {
      await deleteAnyShare(share.id)
      setShares((prev) => prev.filter((s) => s.id !== share.id))
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Error al revocar')
    }
  }

  if (error) return <p className="text-destructive">{error}</p>
  if (loading) return <p className="text-muted-foreground">Cargando...</p>

  return (
    <div>
      <h1 className="text-xl font-semibold mb-6">Wikis compartidas</h1>

      {shares.length === 0 ? (
        <p className="text-sm text-muted-foreground">No hay ninguna wiki compartida.</p>
      ) : (
        <div className="rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 text-left font-medium">Wiki</th>
                <th className="px-4 py-2.5 text-left font-medium">Propietario</th>
                <th className="px-4 py-2.5 text-left font-medium">Compartida con</th>
                <th className="px-4 py-2.5 text-left font-medium">Acceso</th>
                <th className="px-4 py-2.5 text-left font-medium">Fecha</th>
                <th className="px-4 py-2.5 text-right font-medium">Acción</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {shares.map((share) => (
                <tr key={share.id} className="hover:bg-muted/20">
                  <td className="px-4 py-2.5 font-medium">{share.kb_name}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">{share.owner_email}</td>
                  <td className="px-4 py-2.5">
                    <div>{share.shared_with_display_name}</div>
                    <div className="text-xs text-muted-foreground">{share.shared_with_email}</div>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      share.access_level === 'editor'
                        ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
                        : 'bg-muted text-muted-foreground'
                    }`}>
                      {share.access_level === 'editor' ? 'Editar' : 'Ver'}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground">
                    {new Date(share.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => handleRevoke(share)}
                      className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors cursor-pointer"
                      title="Revocar acceso"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
