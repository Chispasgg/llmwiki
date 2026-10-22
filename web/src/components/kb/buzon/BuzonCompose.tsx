'use client'

/**
 * BuzonCompose — sheet modal para redactar mensajes del buzón (BL-005).
 *
 * Presentacional: gestiona su propio estado de formulario pero delega
 * el envío al padre vía `onSend(payload)`. No llama a la API directamente.
 */

import * as React from 'react'
import { X, Plus } from 'lucide-react'
import type { InboxItem, Tipo } from './buzonTypes'
import { buildPreviewLine } from './buzonRender'
import styles from './buzon.module.css'

// ── Contratos públicos ────────────────────────────────────────────────────────

export interface ComposePayload {
  recipient_doc_id: string
  tipo: Tipo
  texto: string
  plazo: string | null
  reply_to: string | null
  enlaces: { label: string; url: string }[] | null
}

export interface BuzonComposeProps {
  open: boolean
  onClose: () => void
  /** Lista de buzones disponibles para el <select> de destinatario. */
  inboxes: InboxItem[]
  /** Cuando `true`, el botón Enviar se muestra deshabilitado. */
  sending?: boolean
  onSend: (payload: ComposePayload) => void
}

// ── Constante local ───────────────────────────────────────────────────────────

const TIPOS: Tipo[] = ['Mensaje', 'Tarea', 'Pendiente', 'Respuesta']

// ── Componente ────────────────────────────────────────────────────────────────

export function BuzonCompose({ open, onClose, inboxes, sending, onSend }: BuzonComposeProps) {
  const [recipientDocId, setRecipientDocId] = React.useState('')
  const [tipo, setTipo] = React.useState<Tipo>('Mensaje')
  const [texto, setTexto] = React.useState('')
  const [plazo, setPlazo] = React.useState('')
  const [replyTo, setReplyTo] = React.useState('')
  const [enlaces, setEnlaces] = React.useState<{ label: string; url: string }[]>([])
  const [err, setErr] = React.useState('')

  // Resetea el formulario cada vez que el sheet se abre.
  // El reset NO va en onClose — onClose solo cierra la UI.
  React.useEffect(() => {
    if (open) {
      setRecipientDocId('')
      setTipo('Mensaje')
      setTexto('')
      setPlazo('')
      setReplyTo('')
      setEnlaces([])
      setErr('')
    }
  }, [open])

  // Cierra el sheet al pulsar Escape
  React.useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  // Preview en vivo de la línea que generará el servidor (con slugs placeholder)
  const previewLine = React.useMemo(() => {
    if (!texto) return ''
    return buildPreviewLine({ tipo, texto, plazo, replyTo, enlaces })
  }, [tipo, texto, plazo, replyTo, enlaces])

  // ── Gestión de enlaces ────────────────────────────────────────────────────

  const handleAddEnlace = () => setEnlaces((prev) => [...prev, { label: '', url: '' }])

  const handleRemoveEnlace = (idx: number) =>
    setEnlaces((prev) => prev.filter((_, i) => i !== idx))

  const handleEnlaceChange = (idx: number, field: 'label' | 'url', value: string) =>
    setEnlaces((prev) => prev.map((e, i) => (i === idx ? { ...e, [field]: value } : e)))

  // ── Submit ────────────────────────────────────────────────────────────────

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!recipientDocId) {
      setErr('Selecciona un destinatario')
      return
    }
    if (!texto.trim()) {
      setErr('Escribe el texto del mensaje')
      return
    }
    setErr('')
    const filtered = enlaces.filter((en) => en.label && en.url)
    const payload: ComposePayload = {
      recipient_doc_id: recipientDocId,
      tipo,
      texto: texto.trim(),
      plazo: plazo.trim() || null,
      reply_to: replyTo.trim() || null,
      enlaces: filtered.length > 0 ? filtered : null,
    }
    onSend(payload)
  }

  // ── Render ────────────────────────────────────────────────────────────────

  if (!open) return null

  return (
    <>
      {/* Backdrop: click fuera cierra el sheet */}
      <div className={styles['sheet-bg']} onClick={onClose} aria-hidden="true" />

      <div role="dialog" aria-modal="true" aria-label="Redactar mensaje" className={styles.sheet}>
        <form className={styles.form} onSubmit={handleSubmit}>

          <header>
            <h2>Redactar</h2>
            <button type="button" className={styles.btn} onClick={onClose} aria-label="Cerrar">
              <X size={16} />
            </button>
          </header>

          {/* Destinatario */}
          <label>
            Destinatario
            <select value={recipientDocId} onChange={(e) => setRecipientDocId(e.target.value)}>
              <option value="">Seleccionar buzón…</option>
              {inboxes.map((inbox) => (
                <option key={inbox.doc_id} value={inbox.doc_id}>
                  {inbox.display} ({inbox.email})
                </option>
              ))}
            </select>
          </label>

          {/* Tipo */}
          <label>
            Tipo
            <select
              value={tipo}
              onChange={(e) => {
                const newTipo = e.target.value as Tipo
                setTipo(newTipo)
                // Limpiar reply_to cuando el tipo deja de ser 'Respuesta'
                // para evitar enviar un reply_to obsoleto en el payload.
                if (newTipo !== 'Respuesta') setReplyTo('')
              }}
            >
              {TIPOS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>

          {/* Plazo y Reply-to en rejilla de 2 columnas */}
          <div className={styles.grid2}>
            <label>
              Plazo <span className={styles.hint}>(opcional, DD/MM)</span>
              <input
                type="text"
                value={plazo}
                onChange={(e) => setPlazo(e.target.value)}
                placeholder="ej. 25/10"
              />
            </label>
            {tipo === 'Respuesta' && (
              <label>
                Respuesta a (ID)
                <input
                  type="text"
                  value={replyTo}
                  onChange={(e) => setReplyTo(e.target.value)}
                  placeholder="ej. 20261021-1030-alice-bob"
                />
              </label>
            )}
          </div>

          {/* Texto del mensaje */}
          <label>
            Mensaje
            <textarea
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder="sin saltos de línea"
            />
          </label>

          {/* Enlaces opcionales */}
          <div className={styles['enlace-section']}>
            {/* Cabecera de sección con botón Añadir */}
            <div className={styles['enlace-header']}>
              <span>
                Enlaces <span className={styles.hint}>(opcionales)</span>
              </span>
              <button
                type="button"
                className={`${styles.btn} ${styles.sm}`}
                onClick={handleAddEnlace}
              >
                <Plus size={13} />
                Añadir
              </button>
            </div>
            {enlaces.map((enlace, idx) => (
              <div key={idx} className={styles['enlace-row']}>
                <input
                  type="text"
                  value={enlace.label}
                  onChange={(e) => handleEnlaceChange(idx, 'label', e.target.value)}
                  placeholder="Etiqueta"
                />
                <input
                  type="url"
                  value={enlace.url}
                  onChange={(e) => handleEnlaceChange(idx, 'url', e.target.value)}
                  placeholder="https://…"
                />
                <button
                  type="button"
                  className={`${styles.btn} ${styles.sm}`}
                  onClick={() => handleRemoveEnlace(idx)}
                  aria-label="Eliminar enlace"
                >
                  <X size={13} />
                </button>
              </div>
            ))}
          </div>  {/* .enlace-section */}

          {/* Preview en vivo — solo visible cuando hay texto */}
          {previewLine && (
            <div className={styles.preview}>
              <span>Previsualización — el slug real lo pone el servidor</span>
              <pre>{previewLine}</pre>
            </div>
          )}

          {/* Footer: error + Cancelar + Enviar */}
          <footer>
            {err && <p className={styles.err}>{err}</p>}
            <span className={styles.spacer} />
            <button type="button" className={styles.btn} onClick={onClose}>
              Cancelar
            </button>
            <button
              type="submit"
              className={`${styles.btn} ${styles.primary}`}
              disabled={sending || !recipientDocId || !texto.trim()}
            >
              {sending ? 'Enviando…' : 'Enviar'}
            </button>
          </footer>

        </form>
      </div>
    </>
  )
}
