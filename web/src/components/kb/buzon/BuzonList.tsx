'use client'

import styles from './buzon.module.css'
import { Avatar } from './ui/Avatar'
import { Chip } from './ui/Chip'
import { estadoToChip, plazoToChip, type EstadoVariant } from './buzonFormat'
import {
  groupByDay,
  type BuzonRow,
} from './buzonListHelpers'
import type { ParsedMessage } from './buzonTypes'

// Re-exports so callers can import BuzonRow from this module.
export type { BuzonRow } from './buzonListHelpers'
export { dayLabel, groupByDay } from './buzonListHelpers'

// ── Public types ──────────────────────────────────────────────────────────────

export interface BuzonListProps {
  rows: BuzonRow[]
  selectedId: string | null
  onSelect: (id: string) => void
  loading?: boolean
  /** Texto del estado vacío (p. ej. "No hay mensajes"). */
  emptyText?: string
}

// ── Chip mapping helpers ───────────────────────────────────────────────────────

/** Devuelve el kind de chip CSS para el tipo del mensaje, o undefined para neutro. */
function tipoKind(tipo: ParsedMessage['tipo']): string | undefined {
  if (tipo === 'Tarea') return 't-task'
  if (tipo === 'Pendiente') return 't-pend'
  if (tipo === 'Respuesta') return 't-reply'
  // 'Mensaje' y null → chip neutro (sin kind)
  return undefined
}

/**
 * Devuelve el kind de chip CSS para la variante de estado, o undefined para neutro.
 * La ausencia de 'seen' es intencional: el estado "visto" se muestra con chip neutro.
 */
function estadoKind(variant: EstadoVariant): string | undefined {
  const map: Partial<Record<EstadoVariant, string>> = {
    rejected: 's-rejected',
    done: 's-done',
    accepted: 's-accepted',
    new: 's-new',
    // 'seen' → ausencia intencional: chip neutro sin énfasis (ver buzon.module.css)
  }
  return map[variant]
}

// ── Component ─────────────────────────────────────────────────────────────────

// CSS Modules expone clases con índice string; necesitamos acceso dinámico
// para nombres con guión (row-main, row-top…) y variantes runtime.
const s = styles as Record<string, string>

const SKELETON_COUNT = [0, 1, 2, 3] as const

export function BuzonList({
  rows,
  selectedId,
  onSelect,
  loading,
  emptyText,
}: BuzonListProps) {
  if (loading) {
    return (
      <div className={s.list}>
        {SKELETON_COUNT.map((i) => (
          <div key={i} className={s.skel} />
        ))}
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <div className={s.list}>
        <div className={s.empty}>
          <strong>{emptyText ?? 'No hay mensajes'}</strong>
        </div>
      </div>
    )
  }

  const groups = groupByDay(rows)

  return (
    <div className={s.list}>
      <div className={s.rows}>
        {groups.map((group) => (
          <div key={group.key}>
            <div className={s.day}>{group.label}</div>
            {group.rows.map((row) => {
              const p = row.parsed
              const estadoChip = p ? estadoToChip(p.estados) : null
              const plazoChip = p ? plazoToChip(p.plazo) : null
              const isUnread = p !== null && !p.closed && estadoChip?.variant === 'new'
              const isClosed = p?.closed ?? false
              const isSelected = row.id !== null && row.id === selectedId

              const rowCls = [
                s.row,
                isUnread ? s.unread : '',
                isClosed ? s.closed : '',
                isSelected ? s.sel : '',
              ]
                .filter(Boolean)
                .join(' ')

              const hora = p?.id_parts.hora
              const horaStr =
                hora && hora.length >= 4
                  ? `${hora.slice(0, 2)}:${hora.slice(2, 4)}`
                  : null

              return (
                <button
                  key={row.key}
                  type="button"
                  className={rowCls}
                  onClick={() => {
                    if (row.id !== null) onSelect(row.id)
                  }}
                >
                  <span className={s.dot} />
                  <Avatar name={row.who} />
                  <div className={s['row-main']}>
                    <div className={s['row-top']}>
                      <b>{row.who}</b>
                      {horaStr && <time>{horaStr}</time>}
                    </div>
                    <p className={s['row-subj']}>{p ? p.body : row.raw}</p>
                    {p && estadoChip && (
                      <div className={s['row-meta']}>
                        {p.tipo && (
                          <Chip kind={tipoKind(p.tipo)}>{p.tipo}</Chip>
                        )}
                        <Chip kind={estadoKind(estadoChip.variant)}>
                          {estadoChip.label}
                        </Chip>
                        {plazoChip && (
                          <Chip kind={`d-${plazoChip.variant}`}>
                            {plazoChip.label}
                          </Chip>
                        )}
                      </div>
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
