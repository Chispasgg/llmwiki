'use client'

import styles from '../buzon.module.css'
import { hueFromName } from '../buzonFormat'

interface AvatarProps {
  name: string
  size?: 'md' | 'lg'
}

/**
 * Avatar circular con inicial(es) del nombre.
 * El color de fondo y texto se derivan de `hueFromName` para que
 * cada persona tenga un tono propio sin configuración manual.
 */
export function Avatar({ name, size }: AvatarProps) {
  // Primera letra de cada palabra, máximo 2 caracteres
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('')

  const cls = [styles.av, size === 'lg' ? styles.lg : ''].filter(Boolean).join(' ')

  return (
    // El único inline style está justificado: --h es un valor dinámico (por persona)
    // que no puede resolverse en tiempo de compilación ni en CSS estático.
    <span
      className={cls}
      aria-label={name}
      style={{ ['--h' as string]: hueFromName(name) }}
    >
      {initials}
    </span>
  )
}
