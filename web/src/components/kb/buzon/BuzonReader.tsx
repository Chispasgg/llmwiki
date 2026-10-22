'use client'

/**
 * BuzonReader — panel lector presentacional del buzón.
 * Clona la columna lector del cliente de Tayfun.
 * Presentacional puro: recibe todo por props y delega las acciones
 * a los callbacks de BuzonReaderActions (BL-006 cableará la lógica).
 */

import * as React from 'react'
import { Check, X, Loader2, Link, BookOpen, GitMerge, ExternalLink } from 'lucide-react'
import styles from './buzon.module.css'
import { Chip } from './ui/Chip'
import { Avatar } from './ui/Avatar'
import { renderBody, extractLinks, refKind, type RefKind } from './buzonRender'
import type { ParsedMessage } from './buzonTypes'

// CSS Modules expone las clases con índice string; necesitamos acceso dinámico
// para nombres con guión (reader-scroll, r-top…) y variantes runtime.
const s = styles as Record<string, string>

// ── Contratos públicos ─────────────────────────────────────────────────────────

export interface BuzonReaderActions {
  submitting?: boolean
  onVisto: () => void
  onAccept: (text: string) => void
  onDone: (text: string) => void
  onReject: (text: string) => void
  onClose: () => void
}

export interface BuzonReaderProps {
  row: { who: string; parsed: ParsedMessage | null; raw: string } | null
  /** Presente solo si el mensaje es accionable (mi buzón, abierto). */
  actions?: BuzonReaderActions
  /** Texto del estado vacío cuando row === null. */
  emptyText?: string
}

// ── tipo de acción con input inline ───────────────────────────────────────────

type ActionKind = 'accept' | 'done' | 'reject'

// ── Helpers puros ─────────────────────────────────────────────────────────────

/** Etiqueta corta a partir de un token de estado. */
function estadoLabel(estado: string): string {
  if (/^visto/i.test(estado)) return 'visto'
  if (/^aceptado/i.test(estado)) return 'aceptado'
  if (/^hecho/i.test(estado)) return 'hecho'
  if (/^rechazado/i.test(estado)) return 'rechazado'
  // Primera palabra para estados desconocidos
  return estado.split(/\s/)[0] ?? estado
}

/** Formatea fecha YYYYMMDD + hora HHMM → "DD/MM/YYYY HH:MM". */
function formatFechaHora(fecha: string, hora: string): string {
  if (fecha.length < 8 || hora.length < 4) return ''
  const d = fecha.slice(6, 8)
  const m = fecha.slice(4, 6)
  const y = fecha.slice(0, 4)
  const hh = hora.slice(0, 2)
  const mm = hora.slice(2, 4)
  return `${d}/${m}/${y} ${hh}:${mm}`
}

/** Devuelve el kind de chip CSS para el tipo del mensaje. */
function tipoKind(tipo: ParsedMessage['tipo']): string | undefined {
  if (tipo === 'Tarea') return 't-task'
  if (tipo === 'Pendiente') return 't-pend'
  if (tipo === 'Respuesta') return 't-reply'
  // 'Mensaje' y null → chip neutro
  return undefined
}

/** Icono para el tipo de referencia. */
function refIcon(kind: RefKind) {
  if (kind === 'jira') return <ExternalLink size={14} />
  if (kind === 'mr') return <GitMerge size={14} />
  if (kind === 'wiki') return <BookOpen size={14} />
  return <Link size={14} />
}

// ── Componente ─────────────────────────────────────────────────────────────────

export function BuzonReader({ row, actions, emptyText }: BuzonReaderProps) {
  // Estado LOCAL: qué acción inline está abierta y su texto.
  // El componente NO formatea el string de estado final; solo recoge el texto
  // y lo pasa al callback — el padre (BL-006) construye el estado definitivo.
  const [openAction, setOpenAction] = React.useState<ActionKind | null>(null)
  const [actionText, setActionText] = React.useState('')

  // Resetear el estado local cuando cambia la fila seleccionada
  React.useEffect(() => {
    setOpenAction(null)
    setActionText('')
  }, [row])

  // ── Estado vacío ────────────────────────────────────────────────────────────

  if (row === null) {
    return (
      <div className={s.reader}>
        <div className={s['reader-empty']}>
          {emptyText ?? 'Selecciona un mensaje'}
        </div>
      </div>
    )
  }

  // ── Datos derivados ─────────────────────────────────────────────────────────

  const p = row.parsed
  const refs = p ? extractLinks(p.body) : []

  // Asunto: primera línea/frase del cuerpo; si no hay parsed, muestra raw
  const asunto = p
    ? (p.body.split(/[.!?\n]/)[0] ?? p.body).trim() || p.body
    : row.raw

  const fechaHora = p
    ? formatFechaHora(p.id_parts.fecha, p.id_parts.hora)
    : ''

  // Timeline: primer pip "recibido" siempre on; luego un paso por cada estado
  const timelineSteps = [
    { label: 'recibido', bad: false },
    ...(p?.estados ?? []).map((e) => ({
      label: estadoLabel(e),
      bad: /rechazado/i.test(e),
    })),
  ]
  const lastStepIdx = timelineSteps.length - 1

  const showActions = !!actions && !p?.closed

  // ── Manejadores de la barra de acciones ────────────────────────────────────

  function toggleAction(kind: ActionKind) {
    // Si ya está abierta esta acción, ciérrala; si no, ábrela
    if (openAction === kind) {
      setOpenAction(null)
      setActionText('')
    } else {
      setOpenAction(kind)
      setActionText('')
    }
  }

  function confirmAction() {
    if (!openAction || !actionText.trim() || !actions) return
    const text = actionText.trim()
    if (openAction === 'accept') actions.onAccept(text)
    else if (openAction === 'done') actions.onDone(text)
    else actions.onReject(text)
    setOpenAction(null)
    setActionText('')
  }

  function handleInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') confirmAction()
    if (e.key === 'Escape') {
      setOpenAction(null)
      setActionText('')
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className={s.reader}>
      <div className={s['reader-scroll']}>
        <div className={s['reader-in']}>

          {/* .r-top: chip de tipo + id del mensaje */}
          <div className={s['r-top']}>
            {p?.tipo && (
              <Chip kind={tipoKind(p.tipo)}>{p.tipo}</Chip>
            )}
            {p && (
              <span className={s.idbtn}>{p.id}</span>
            )}
          </div>

          {/* .r-subj: asunto (primera línea del cuerpo) */}
          <p className={s['r-subj']}>{asunto}</p>

          {/* .r-from: avatar grande + nombre + fecha/hora */}
          <div className={s['r-from']}>
            <Avatar name={row.who} size="lg" />
            <div>
              <b>{row.who}</b>
              {fechaHora && <small>{fechaHora}</small>}
            </div>
          </div>

          {/* Timeline .track */}
          <ul className={s.track}>
            {timelineSteps.map((step, i) => {
              const isCur = i === lastStepIdx
              const liCls = [
                s.on,
                isCur ? s.cur : '',
                step.bad ? s.bad : '',
              ]
                .filter(Boolean)
                .join(' ')

              return (
                <li key={i} className={liCls}>
                  <span className={s.pip}>
                    {step.bad ? <X size={10} /> : <Check size={10} />}
                  </span>
                  {step.label}
                </li>
              )
            })}
          </ul>

          {/* .r-body: cuerpo completo con enlaces inline */}
          {p && (
            <div className={s['r-body']}>
              <p>{renderBody(p.body)}</p>
            </div>
          )}

          {/* Sección "Referencias" — solo si hay enlaces http(s) */}
          {refs.length > 0 && (
            <div className={s.sec}>
              <h3>Referencias</h3>
              <div className={s.refs}>
                {refs.map((ref, i) => {
                  const kind = refKind(ref.url)
                  // Compone la clase base .ref con la variante de tipo (jira, mr, wiki)
                  const refCls = [s.ref, s[kind] ?? ''].filter(Boolean).join(' ')
                  return (
                    <a
                      key={i}
                      href={ref.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={refCls}
                    >
                      <span className={s.ic}>{refIcon(kind)}</span>
                      <span>
                        <b>{ref.label}</b>
                        <small>{ref.url}</small>
                      </span>
                    </a>
                  )
                })}
              </div>
            </div>
          )}

          {/* Línea original (colapsable) */}
          <details className={s.raw}>
            <summary>Línea original</summary>
            <pre>{row.raw}</pre>
          </details>

        </div>
      </div>

      {/* Barra .actions — solo si el mensaje es accionable y no está cerrado */}
      {showActions && (
        <div className={s.actions}>
          {actions.submitting ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <>
              <button
                type="button"
                className={[s.btn, s.sm].join(' ')}
                onClick={actions.onVisto}
              >
                Visto
              </button>
              <button
                type="button"
                className={[s.btn, s.sm].join(' ')}
                onClick={() => toggleAction('accept')}
              >
                Aceptado
              </button>
              <button
                type="button"
                className={[s.btn, s.sm].join(' ')}
                onClick={() => toggleAction('done')}
              >
                Hecho
              </button>
              <button
                type="button"
                className={[s.btn, s.sm, s.danger].join(' ')}
                onClick={() => toggleAction('reject')}
              >
                Rechazado
              </button>
              <button
                type="button"
                className={[s.btn, s.sm].join(' ')}
                onClick={actions.onClose}
              >
                Cerrar
              </button>
            </>
          )}

          {/* Input inline para acciones que requieren texto */}
          {openAction && !actions.submitting && (
            <>
              <input
                type="text"
                className={s['act-input']}
                value={actionText}
                onChange={(e) => setActionText(e.target.value)}
                onKeyDown={handleInputKeyDown}
                placeholder={
                  openAction === 'accept'
                    ? 'Nota o enlace (aceptado → …)'
                    : openAction === 'done'
                      ? 'URL o fecha DD/MM (hecho → …)'
                      : 'Motivo (rechazado: …)'
                }
                autoFocus
              />
              <button
                type="button"
                className={[s.btn, s.sm, s.primary].join(' ')}
                onClick={confirmAction}
              >
                OK
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
