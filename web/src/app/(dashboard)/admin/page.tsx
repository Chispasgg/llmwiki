'use client'

import { useEffect, useState } from 'react'
import { getGlobalStats, type GlobalStats } from '@/lib/admin'

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  )
}

function fmtBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 ** 2) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1024 ** 3) return `${(b / 1024 ** 2).toFixed(1)} MB`
  return `${(b / 1024 ** 3).toFixed(2)} GB`
}

export default function AdminOverviewPage() {
  const [stats, setStats] = useState<GlobalStats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getGlobalStats().then(setStats).catch((e) => setError(e.message))
  }, [])

  if (error) return <p className="text-destructive">{error}</p>
  if (!stats) return <p className="text-muted-foreground">Cargando...</p>

  return (
    <div>
      <h1 className="text-xl font-semibold mb-6">Panel de administración</h1>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Usuarios" value={stats.total_users} />
        <StatCard label="Documentos" value={stats.total_documents} />
        <StatCard label="Páginas indexadas" value={stats.total_pages} />
        <StatCard label="Almacenamiento" value={fmtBytes(stats.total_storage_bytes)} />
      </div>
      <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 text-sm text-muted-foreground">
        <p>Máx. usuarios: {stats.global_max_users}</p>
        <p>Máx. páginas/usuario: {stats.quota_max_pages_per_user}</p>
        <p>Máx. almacenamiento/usuario: {fmtBytes(stats.quota_max_storage_per_user)}</p>
      </div>
    </div>
  )
}
