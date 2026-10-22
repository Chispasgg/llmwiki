/**
 * Helpers puros (sin React, sin I/O) para el módulo buzón.
 * Consumidos por la lista (BL-003) y el lector (BL-004).
 * Sin efectos secundarios → testables de forma aislada.
 */

/**
 * Tono HSL determinista en [0, 360) calculado a partir de un nombre.
 * Mismo nombre ⇒ mismo tono; es el valor de `--h` para el avatar.
 */
export function hueFromName(name: string): number {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    // Multiplicar por 31 (primo habitual en hashing de strings) y mantener
    // el resultado como entero de 32 bits para evitar floats y desbordamientos.
    hash = (hash * 31 + name.charCodeAt(i)) | 0
  }
  // % puede devolver negativos en JS si hash < 0; el +360 lo normaliza.
  return ((hash % 360) + 360) % 360
}

// ── Estado ────────────────────────────────────────────────────────────────────

export type EstadoVariant = 'new' | 'accepted' | 'done' | 'rejected' | 'seen'

export interface EstadoChip {
  variant: EstadoVariant
  label: string
}

/**
 * Clasifica el estado global de un mensaje a partir de sus tokens de estado.
 * Prioridad (mayor a menor): rechazado > hecho > aceptado > visto > nuevo.
 */
export function estadoToChip(estados: string[]): EstadoChip {
  for (const e of estados) {
    if (/rechazado/i.test(e)) return { variant: 'rejected', label: 'rechazado' }
  }
  for (const e of estados) {
    if (/hecho/i.test(e)) return { variant: 'done', label: 'hecho' }
  }
  for (const e of estados) {
    if (/aceptado/i.test(e)) return { variant: 'accepted', label: 'aceptado' }
  }
  for (const e of estados) {
    if (/visto/i.test(e)) return { variant: 'seen', label: 'visto' }
  }
  return { variant: 'new', label: 'nuevo' }
}

// ── Plazo ─────────────────────────────────────────────────────────────────────

export type PlazoVariant = 'over' | 'soon'

export interface PlazoChip {
  variant: PlazoVariant
  label: string
}

/**
 * Parsea un plazo en formato DD/MM y devuelve el chip de urgencia.
 * - Vencido (deadline < now)          → { variant: 'over', label: 'vencido' }
 * - Dentro de 3 días                  → { variant: 'soon', label: 'próximo' }
 * - Lejano, nulo o malformado         → null
 *
 * El parámetro `now` es inyectable para que los tests sean deterministas.
 * Criterio idéntico al de `plazoPriority` en BuzonView.tsx (no editar ese fichero).
 */
export function plazoToChip(plazo: string | null, now: Date = new Date()): PlazoChip | null {
  if (!plazo) return null
  const [d, m] = plazo.split('/').map(Number)
  if (!d || !m) return null
  const deadline = new Date(now.getFullYear(), m - 1, d, 23, 59, 59)
  if (deadline < now) return { variant: 'over', label: 'vencido' }
  const diff = deadline.getTime() - now.getTime()
  if (diff < 3 * 24 * 60 * 60 * 1000) return { variant: 'soon', label: 'próximo' }
  return null
}
