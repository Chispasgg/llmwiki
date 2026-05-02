'use client'

import { useEffect, useState } from 'react'
import { listAllKBs, deleteAnyKB, type AdminKB } from '@/lib/admin'

export default function AdminWikisPage() {
  const [kbs, setKbs] = useState<AdminKB[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const load = () => {
    setLoading(true)
    listAllKBs()
      .then(setKbs)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleDelete = async (kb: AdminKB) => {
    if (!confirm(`¿Eliminar la wiki "${kb.name}" de ${kb.user_email}? Esta acción no se puede deshacer.`)) return
    try {
      await deleteAnyKB(kb.id)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const filtered = kbs.filter(
    (kb) =>
      kb.name.toLowerCase().includes(search.toLowerCase()) ||
      kb.user_email.toLowerCase().includes(search.toLowerCase()),
  )

  if (loading) return <p className="text-muted-foreground">Cargando...</p>

  return (
    <div>
      <h1 className="text-xl font-semibold mb-6">Gestión de wikis</h1>
      {error && <p className="text-destructive mb-4">{error}</p>}
      <input
        placeholder="Buscar por nombre o usuario..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="mb-4 border rounded px-3 py-2 text-sm w-72"
      />
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-2 pr-4">Nombre</th>
            <th className="py-2 pr-4">Propietario</th>
            <th className="py-2 pr-4">Slug</th>
            <th className="py-2 pr-4">Compartida</th>
            <th className="py-2 pr-4">Creada</th>
            <th className="py-2">Acción</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((kb) => (
            <tr key={kb.id} className="border-b hover:bg-muted/40">
              <td className="py-2 pr-4 font-medium">{kb.name}</td>
              <td className="py-2 pr-4 text-muted-foreground">{kb.user_email}</td>
              <td className="py-2 pr-4 font-mono text-xs">{kb.slug}</td>
              <td className="py-2 pr-4">
                {kb.is_shared && (
                  <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">Compartida</span>
                )}
              </td>
              <td className="py-2 pr-4 text-muted-foreground">
                {new Date(kb.created_at).toLocaleDateString('es')}
              </td>
              <td className="py-2">
                <button
                  onClick={() => handleDelete(kb)}
                  className="text-xs text-destructive hover:underline"
                >
                  Eliminar
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
