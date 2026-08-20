'use client'

import { useEffect, useState, useCallback } from 'react'
import { getEmbeddingStats, clearEmbeddings, type EmbeddingStats } from '@/lib/admin'

export default function AdminEmbeddingsPage() {
  const [stats, setStats] = useState<EmbeddingStats | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  const load = useCallback(() => {
    getEmbeddingStats().then(setStats).catch((e) => setError(e.message))
  }, [])
  useEffect(load, [load])

  return (
    <div>
      <h1 className="text-xl font-semibold mb-6">Embeddings</h1>
      {error && <p className="text-destructive mb-4">{error}</p>}
      {!stats ? (
        <p className="text-sm text-muted-foreground">Cargando…</p>
      ) : (
        <div className="max-w-xl space-y-4">
          {!stats.ollama_configured && (
            <p className="text-sm text-amber-600">
              OLLAMA_URL no configurado: búsqueda semántica desactivada (solo léxico).
            </p>
          )}
          <p className="text-sm">Modelo: <code>{stats.model}</code></p>
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span>{stats.embedded} / {stats.total} chunks embebidos</span>
              <span>{stats.percent}%</span>
            </div>
            <div className="w-full bg-muted rounded h-3 overflow-hidden">
              <div className="bg-primary h-3" style={{ width: `${stats.percent}%` }} />
            </div>
            <p className="text-xs text-muted-foreground mt-1">{stats.pending} pendientes</p>
          </div>
          <div className="flex gap-3">
            <button onClick={load} className="border rounded px-3 py-2 text-sm">
              Actualizar
            </button>
            <button
              onClick={() => {
                if (!window.confirm('Se borrarán TODOS los embeddings y se regenerarán en segundo plano. ¿Continuar?')) return
                clearEmbeddings()
                  .then((r) => { setMsg(`Borrados ${r.cleared} embeddings. Regenerando…`); load() })
                  .catch((e) => setMsg(`Error: ${e.message}`))
              }}
              className="border rounded px-3 py-2 text-sm bg-destructive/10 text-destructive"
            >
              Borrar y regenerar
            </button>
          </div>
          {msg && <p className="text-sm text-muted-foreground">{msg}</p>}
        </div>
      )}
    </div>
  )
}
