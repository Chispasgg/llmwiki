'use client'

import { useEffect, useState, useCallback } from 'react'
import { listUsageLogs, type UsageLog } from '@/lib/admin'

const ACTION_FILTERS = ['', 'login', 'api_key.create', 'api_key.revoke']

export default function AdminLogsPage() {
  const [logs, setLogs] = useState<UsageLog[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [action, setAction] = useState('')
  const [offset, setOffset] = useState(0)
  const LIMIT = 50

  const load = useCallback(() => {
    setLoading(true)
    listUsageLogs({ limit: LIMIT, offset, action: action || undefined })
      .then(setLogs)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [offset, action])

  useEffect(load, [load])

  const handleActionChange = (v: string) => {
    setAction(v)
    setOffset(0)
  }

  return (
    <div>
      <h1 className="text-xl font-semibold mb-6">Log de uso</h1>
      {error && <p className="text-destructive mb-4">{error}</p>}

      <div className="flex gap-3 mb-4">
        <select
          value={action}
          onChange={(e) => handleActionChange(e.target.value)}
          className="border rounded px-3 py-2 text-sm"
        >
          <option value="">Todas las acciones</option>
          {ACTION_FILTERS.filter(Boolean).map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <button onClick={load} className="border rounded px-3 py-2 text-sm">
          Actualizar
        </button>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Cargando...</p>
      ) : (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="py-2 pr-4">Fecha</th>
              <th className="py-2 pr-4">Usuario</th>
              <th className="py-2 pr-4">Acción</th>
              <th className="py-2 pr-4">Recurso</th>
              <th className="py-2">IP</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id} className="border-b hover:bg-muted/40">
                <td className="py-2 pr-4 text-muted-foreground whitespace-nowrap">
                  {new Date(l.created_at).toLocaleString('es')}
                </td>
                <td className="py-2 pr-4">{l.user_email ?? '—'}</td>
                <td className="py-2 pr-4 font-mono text-xs">{l.action}</td>
                <td className="py-2 pr-4 text-muted-foreground text-xs">
                  {l.resource_type ? `${l.resource_type}:${l.resource_id ?? ''}` : '—'}
                </td>
                <td className="py-2 text-muted-foreground text-xs">{l.ip_address ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="flex gap-3 mt-4">
        <button
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - LIMIT))}
          className="border rounded px-3 py-1 text-sm disabled:opacity-40"
        >
          Anterior
        </button>
        <button
          disabled={logs.length < LIMIT}
          onClick={() => setOffset(offset + LIMIT)}
          className="border rounded px-3 py-1 text-sm disabled:opacity-40"
        >
          Siguiente
        </button>
      </div>
    </div>
  )
}
