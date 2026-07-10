import * as React from 'react'
import { apiFetch } from '@/lib/api'
import type { NameAvailability } from '@/lib/types'

/** Consulta con debounce la normalización + disponibilidad de un nombre de wiki. */
export function useNameAvailability(name: string, excludeKbId?: string) {
  const [state, setState] = React.useState<NameAvailability | null>(null)
  const [checking, setChecking] = React.useState(false)

  React.useEffect(() => {
    const trimmed = name.trim()
    if (!trimmed) {
      setState(null)
      setChecking(false)
      return
    }
    setChecking(true)
    const timer = setTimeout(async () => {
      try {
        const params = new URLSearchParams({ name: trimmed })
        if (excludeKbId) params.set('exclude_kb_id', excludeKbId)
        const data = await apiFetch<NameAvailability>(
          `/v1/kb-name-availability?${params.toString()}`,
        )
        setState(data)
      } catch {
        setState(null)
      } finally {
        setChecking(false)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [name, excludeKbId])

  return { state, checking }
}
