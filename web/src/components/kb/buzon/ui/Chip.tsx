'use client'

import type { ReactNode } from 'react'
import styles from '../buzon.module.css'

interface ChipProps {
  /** Variante de estilo. Acepta: 't-task' | 't-pend' | 't-reply' (tipo),
   *  's-new' | 's-accepted' | 's-done' | 's-rejected' (estado),
   *  'd-over' | 'd-soon' (plazo), 'big' (modificador tamaño).
   *  Sin `kind` → chip neutro con color de fondo por defecto. */
  kind?: string
  children: ReactNode
}

// CSS Modules expone las clases con índice string; necesitamos acceso dinámico
// porque `kind` es determinado en runtime (p.ej. 't-task', 'd-over', …).
const s = styles as Record<string, string>

/**
 * Chip/badge presentacional del módulo buzón.
 * Compone la clase base `.chip` con la variante `kind` cuando se indica.
 */
export function Chip({ kind, children }: ChipProps) {
  const cls = [s.chip, kind ? s[kind] : ''].filter(Boolean).join(' ')

  return <span className={cls}>{children}</span>
}
