/**
 * Helpers puros (sin React, sin I/O) para el panel lista del buzón.
 * Separados del componente BuzonList.tsx para ser testables en bun test
 * sin necesitar el runtime JSX.
 * Sin efectos secundarios → deterministas con `now` inyectable.
 */

import type { ParsedMessage } from './buzonTypes'

// ── Tipos ─────────────────────────────────────────────────────────────────────

/** Fila normalizada que consume BuzonList. */
export interface BuzonRow {
  /** Identificador único de fila (p. ej. índice o id). */
  key: string
  /** Id del mensaje para selección; null si no parseable. */
  id: string | null
  /** Nombre a mostrar: remitente en Recibidos, destinatario en Enviados. */
  who: string
  parsed: ParsedMessage | null
  /** Texto crudo: fallback si parsed === null. */
  raw: string
}

export interface DayGroup {
  key: string
  label: string
  rows: BuzonRow[]
}

// ── Day helpers ───────────────────────────────────────────────────────────────

const NO_DATE_KEY = '__no_date__'

/**
 * Convierte una fecha YYYYMMDD a etiqueta de día legible.
 * El parámetro `now` es inyectable para que los tests sean deterministas.
 */
export function dayLabel(fecha: string, now: Date = new Date()): string {
  if (fecha.length !== 8) return fecha
  const y = parseInt(fecha.slice(0, 4), 10)
  const m = parseInt(fecha.slice(4, 6), 10)
  const d = parseInt(fecha.slice(6, 8), 10)
  if (!y || !m || !d) return fecha

  // Comparación en zona horaria local sin componente de hora.
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const target = new Date(y, m - 1, d)
  const diffDays = Math.round((today.getTime() - target.getTime()) / (24 * 60 * 60 * 1000))

  if (diffDays === 0) return 'HOY'
  if (diffDays === 1) return 'AYER'
  return `${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}/${y}`
}

/**
 * Agrupa filas por día (YYYYMMDD).
 * Las filas sin `parsed` van en un grupo final "Sin fecha".
 * El parámetro `now` es inyectable para tests deterministas.
 */
export function groupByDay(rows: BuzonRow[], now: Date = new Date()): DayGroup[] {
  const map = new Map<string, DayGroup>()

  for (const row of rows) {
    const fecha = row.parsed?.id_parts.fecha ?? null
    const key = fecha ?? NO_DATE_KEY
    if (!map.has(key)) {
      const label = fecha ? dayLabel(fecha, now) : 'Sin fecha'
      map.set(key, { key, label, rows: [] })
    }
    map.get(key)!.rows.push(row)
  }

  // "Sin fecha" siempre al final.
  const result = Array.from(map.values()).filter((g) => g.key !== NO_DATE_KEY)
  const noDate = map.get(NO_DATE_KEY)
  if (noDate) result.push(noDate)
  return result
}
