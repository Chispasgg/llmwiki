'use client'

/**
 * BuzonView — vista nativa de buzón para una KB (modo hosted).
 *
 * Flujo principal:
 *  1. Carga todos los buzones de la KB (GET inboxes).
 *  2. Si no hay buzón propio → pantalla "Crear mi buzón".
 *  3. Si hay buzón → tabs: Recibidos / Enviados / Redactar.
 *
 * Todas las llamadas a la API usan apiFetch, que ya incluye la cookie de sesión.
 * Los errores HTTP se muestran con toast (sonner).
 */

import * as React from 'react'
import {
  Inbox,
  Send,
  PenSquare,
  RefreshCw,
  Plus,
  X,
  Loader2,
  Mail,
  ExternalLink,
  CheckSquare2,
  Square,
} from 'lucide-react'
import { toast } from 'sonner'
import { apiFetch } from '@/lib/api'
import { cn } from '@/lib/utils'

// ── Domain types ──────────────────────────────────────────────────────────────

interface InboxItem {
  doc_id: string
  path: string
  filename: string
  display: string
  email: string
  is_mine: boolean
}

interface IdParts {
  fecha: string
  hora: string
  remitente: string
  destinatario: string | null
  b: boolean
}

interface ParsedMessage {
  closed: boolean
  id: string
  id_parts: IdParts
  tipo: 'Mensaje' | 'Tarea' | 'Pendiente' | 'Respuesta' | null
  reply_to: string | null
  plazo: string | null
  body: string
  estados: string[]
}

interface MessageLine {
  line_index: number
  raw: string
  parsed: ParsedMessage | null
}

interface SentItem {
  inbox: { doc_id: string; display: string; email: string }
  raw: string
  parsed: (ParsedMessage & { remitente_slug?: string }) | null
}

type Tipo = 'Mensaje' | 'Tarea' | 'Pendiente' | 'Respuesta'
const TIPOS: Tipo[] = ['Mensaje', 'Tarea', 'Pendiente', 'Respuesta']

type Tab = 'recibidos' | 'enviados' | 'redactar'

// Tracks a status action that requires text input before submission
interface PendingStatusInput {
  lineId: string
  buzonDocId: string
  action: 'aceptado' | 'hecho' | 'rechazado'
  text: string
}

// ── Pure helpers ──────────────────────────────────────────────────────────────

function todayDDMM(): string {
  const d = new Date()
  return `${d.getDate()}/${d.getMonth() + 1}`
}

type PlazoPriority = 'overdue' | 'soon' | null

function plazoPriority(plazo: string): PlazoPriority {
  const [d, m] = plazo.split('/').map(Number)
  if (!d || !m) return null
  const now = new Date()
  const deadline = new Date(now.getFullYear(), m - 1, d, 23, 59, 59)
  if (deadline < now) return 'overdue'
  const diff = deadline.getTime() - now.getTime()
  if (diff < 3 * 24 * 60 * 60 * 1000) return 'soon'
  return null
}

/**
 * Client-side preview of a buzón line.
 * Uses "yo" as sender slug (not known client-side) and "destinatario" as placeholder.
 * The server will produce the real line with correct slugs.
 */
function buildPreviewLine(opts: {
  tipo: Tipo
  texto: string
  plazo: string
  replyTo: string
  enlaces: { label: string; url: string }[]
}): string {
  const FIELD_SEP = ' · '
  const BODY_SEP = ' — '
  const now = new Date()
  const fecha = now.toISOString().slice(0, 10).replace(/-/g, '')
  const hora = `${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`

  const idStr = `${fecha}-${hora}-yo-destinatario`
  const headerParts: string[] = [idStr]
  if (opts.tipo === 'Respuesta' && opts.replyTo) {
    headerParts.push(`Respuesta a ${opts.replyTo}`)
  } else {
    headerParts.push(opts.tipo)
  }
  if (opts.plazo) headerParts.push(`plazo ${opts.plazo}`)

  const bodyParts: string[] = [opts.texto || '(texto vacío)']
  for (const { label, url } of opts.enlaces) {
    if (label && url) bodyParts.push(`[${label}](${url})`)
  }

  return `- [ ] ${headerParts.join(FIELD_SEP)}${BODY_SEP}${bodyParts.join(FIELD_SEP)}`
}

/** Render a body string with markdown-style [label](url) links.
 *
 * Only renders an <a> when the URL starts with http:// or https://.
 * Any other scheme (javascript:, data:, vbscript:, …) is rendered as
 * plain text — clicking a non-http/s URL could execute stored XSS.
 */
function renderBody(body: string): React.ReactNode {
  const parts = body.split(/(\[[^\]]+\]\([^)]+\))/)
  return (
    <>
      {parts.map((part, i) => {
        const match = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
        if (match) {
          const url = match[2]
          // Reject any scheme that is not http/https — covers javascript:, data:, etc.
          if (!/^https?:\/\//i.test(url)) {
            return <React.Fragment key={i}>{part}</React.Fragment>
          }
          return (
            <a
              key={i}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-0.5 text-primary underline underline-offset-2 hover:opacity-80"
            >
              {match[1]}
              <ExternalLink className="size-2.5 opacity-60" />
            </a>
          )
        }
        return <React.Fragment key={i}>{part}</React.Fragment>
      })}
    </>
  )
}

const TIPO_COLORS: Record<string, string> = {
  Mensaje: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  Tarea: 'bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400',
  Pendiente: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  Respuesta: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
}

function TipoBadge({ tipo }: { tipo: string | null }) {
  if (!tipo) return null
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium shrink-0',
        TIPO_COLORS[tipo] ?? 'bg-muted text-muted-foreground',
      )}
    >
      {tipo}
    </span>
  )
}

// ── BuzonView ─────────────────────────────────────────────────────────────────

export interface BuzonViewProps {
  kbId: string
}

export function BuzonView({ kbId }: BuzonViewProps) {
  // ── Inbox resolution ─────────────────────────────────────────────────────
  const [inboxes, setInboxes] = React.useState<InboxItem[]>([])
  const [loadingInboxes, setLoadingInboxes] = React.useState(true)
  const [creatingInbox, setCreatingInbox] = React.useState(false)

  const myInbox = React.useMemo(
    () => inboxes.find((i) => i.is_mine) ?? null,
    [inboxes],
  )

  const loadInboxes = React.useCallback(async () => {
    setLoadingInboxes(true)
    try {
      const data = await apiFetch<InboxItem[]>(
        `/v1/knowledge-bases/${kbId}/buzon/inboxes`,
      )
      setInboxes(data)
    } catch (err) {
      toast.error((err as Error).message || 'Error al cargar buzones')
    } finally {
      setLoadingInboxes(false)
    }
  }, [kbId])

  React.useEffect(() => {
    void loadInboxes()
  }, [loadInboxes])

  const handleCreateInbox = async () => {
    setCreatingInbox(true)
    try {
      await apiFetch(`/v1/knowledge-bases/${kbId}/buzon/mine`, {
        method: 'POST',
        body: JSON.stringify({}),
      })
      await loadInboxes()
      toast.success('Buzón creado')
    } catch (err) {
      toast.error((err as Error).message || 'Error al crear buzón')
    } finally {
      setCreatingInbox(false)
    }
  }

  // ── Tabs ─────────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = React.useState<Tab>('recibidos')

  // ── Recibidos ─────────────────────────────────────────────────────────────
  const [messages, setMessages] = React.useState<MessageLine[]>([])
  const [loadingMessages, setLoadingMessages] = React.useState(false)

  const loadMessages = React.useCallback(
    async (docId: string) => {
      setLoadingMessages(true)
      try {
        const data = await apiFetch<MessageLine[]>(
          `/v1/knowledge-bases/${kbId}/buzon/inboxes/${docId}/messages`,
        )
        setMessages(data)
      } catch (err) {
        toast.error((err as Error).message || 'Error al cargar mensajes')
      } finally {
        setLoadingMessages(false)
      }
    },
    [kbId],
  )

  React.useEffect(() => {
    if (myInbox && activeTab === 'recibidos') {
      void loadMessages(myInbox.doc_id)
    }
  }, [myInbox, activeTab, loadMessages])

  // ── Status actions ────────────────────────────────────────────────────────
  // submittingStatus: lineId currently being saved (shows spinner on that row)
  const [submittingStatus, setSubmittingStatus] = React.useState<string | null>(null)
  // pendingInput: when an action requires text input before submitting
  const [pendingInput, setPendingInput] = React.useState<PendingStatusInput | null>(null)

  const submitStatus = React.useCallback(
    async (opts: {
      lineId: string
      buzonDocId: string
      estado?: string | null
      closed?: boolean | null
    }) => {
      setSubmittingStatus(opts.lineId)
      try {
        await apiFetch(`/v1/knowledge-bases/${kbId}/buzon/status`, {
          method: 'POST',
          body: JSON.stringify({
            buzon_doc_id: opts.buzonDocId,
            line_id: opts.lineId,
            estado: opts.estado ?? null,
            closed: opts.closed ?? null,
          }),
        })
        // Reload to reflect the new state
        if (myInbox) await loadMessages(myInbox.doc_id)
      } catch (err) {
        toast.error((err as Error).message || 'Error al actualizar estado')
      } finally {
        setSubmittingStatus(null)
        setPendingInput(null)
      }
    },
    [kbId, myInbox, loadMessages],
  )

  const handleVisto = React.useCallback(
    (lineId: string, buzonDocId: string) => {
      void submitStatus({ lineId, buzonDocId, estado: `visto ${todayDDMM()}` })
    },
    [submitStatus],
  )

  const handleCerrar = React.useCallback(
    (lineId: string, buzonDocId: string) => {
      void submitStatus({ lineId, buzonDocId, closed: true })
    },
    [submitStatus],
  )

  const handleInputAction = React.useCallback(
    (lineId: string, buzonDocId: string, action: PendingStatusInput['action']) => {
      // If already showing this line's input, toggle it off
      if (pendingInput?.lineId === lineId && pendingInput.action === action) {
        setPendingInput(null)
        return
      }
      setPendingInput({ lineId, buzonDocId, action, text: '' })
    },
    [pendingInput],
  )

  const confirmInputAction = React.useCallback(async () => {
    if (!pendingInput) return
    const { lineId, buzonDocId, action, text } = pendingInput
    // Strip newlines before composing estado: pasted multiline text would
    // produce a malformed state string and an opaque 400 from the backend.
    const cleanText = text.replace(/[\r\n]+/g, ' ').trim()
    if (!cleanText) {
      toast.error('Escribe el texto antes de confirmar')
      return
    }
    let estado: string
    if (action === 'aceptado') {
      estado = `aceptado → ${cleanText}`
    } else if (action === 'hecho') {
      // DD/MM format → "hecho DD/MM", otherwise → "hecho → <url>"
      const isDate = /^\d{1,2}\/\d{1,2}$/.test(cleanText)
      estado = isDate ? `hecho ${cleanText}` : `hecho → ${cleanText}`
    } else {
      estado = `rechazado: ${cleanText}`
    }
    await submitStatus({ lineId, buzonDocId, estado })
  }, [pendingInput, submitStatus])

  // ── Enviados ──────────────────────────────────────────────────────────────
  const [sent, setSent] = React.useState<SentItem[]>([])
  const [loadingSent, setLoadingSent] = React.useState(false)

  const loadSent = React.useCallback(async () => {
    setLoadingSent(true)
    try {
      const data = await apiFetch<SentItem[]>(
        `/v1/knowledge-bases/${kbId}/buzon/sent`,
      )
      setSent(data)
    } catch (err) {
      toast.error((err as Error).message || 'Error al cargar enviados')
    } finally {
      setLoadingSent(false)
    }
  }, [kbId])

  React.useEffect(() => {
    if (activeTab === 'enviados') {
      void loadSent()
    }
  }, [activeTab, loadSent])

  // ── Redactar ──────────────────────────────────────────────────────────────
  const [recipientDocId, setRecipientDocId] = React.useState('')
  const [tipo, setTipo] = React.useState<Tipo>('Mensaje')
  const [texto, setTexto] = React.useState('')
  const [plazo, setPlazo] = React.useState('')
  const [replyTo, setReplyTo] = React.useState('')
  const [enlaces, setEnlaces] = React.useState<{ label: string; url: string }[]>([])
  const [showPreview, setShowPreview] = React.useState(false)
  const [sending, setSending] = React.useState(false)
  const [lastSentLine, setLastSentLine] = React.useState<string | null>(null)

  const previewLine = React.useMemo(() => {
    if (!texto.trim()) return null
    return buildPreviewLine({ tipo, texto, plazo, replyTo, enlaces })
  }, [tipo, texto, plazo, replyTo, enlaces])

  const handleAddEnlace = () => {
    setEnlaces((prev) => [...prev, { label: '', url: '' }])
  }

  const handleRemoveEnlace = (idx: number) => {
    setEnlaces((prev) => prev.filter((_, i) => i !== idx))
  }

  const handleEnlaceChange = (idx: number, field: 'label' | 'url', value: string) => {
    setEnlaces((prev) =>
      prev.map((e, i) => (i === idx ? { ...e, [field]: value } : e)),
    )
  }

  const handleSend = async () => {
    if (!recipientDocId) {
      toast.error('Selecciona un destinatario')
      return
    }
    if (!texto.trim()) {
      toast.error('Escribe el texto del mensaje')
      return
    }
    setSending(true)
    try {
      const result = await apiFetch<{ line: string; ok: boolean }>(
        `/v1/knowledge-bases/${kbId}/buzon/send`,
        {
          method: 'POST',
          body: JSON.stringify({
            recipient_doc_id: recipientDocId,
            tipo,
            texto: texto.trim(),
            plazo: plazo.trim() || null,
            reply_to: replyTo.trim() || null,
            enlaces:
              enlaces.filter((e) => e.label && e.url).length > 0
                ? enlaces.filter((e) => e.label && e.url)
                : null,
          }),
        },
      )
      setLastSentLine(result.line)
      setTexto('')
      setPlazo('')
      setReplyTo('')
      setEnlaces([])
      setShowPreview(false)
      toast.success('Mensaje enviado')
      setActiveTab('enviados')
      void loadSent()
    } catch (err) {
      toast.error((err as Error).message || 'Error al enviar')
    } finally {
      setSending(false)
    }
  }

  const handleRefresh = () => {
    if (activeTab === 'recibidos' && myInbox) void loadMessages(myInbox.doc_id)
    if (activeTab === 'enviados') void loadSent()
  }

  // ── Render: loading / no inbox ─────────────────────────────────────────────

  if (loadingInboxes) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!myInbox) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 px-6">
        <Mail className="size-10 text-muted-foreground/20" />
        <div className="text-center max-w-sm">
          <h3 className="text-base font-medium mb-1.5">Sin buzón propio</h3>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Crea tu buzón para poder recibir y enviar mensajes en esta KB.
          </p>
        </div>
        <button
          onClick={() => void handleCreateInbox()}
          disabled={creatingInbox}
          className="inline-flex items-center gap-2 rounded-full bg-foreground text-background px-5 py-2 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50 cursor-pointer"
        >
          {creatingInbox ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Plus className="size-3.5" />
          )}
          Crear mi buzón
        </button>
      </div>
    )
  }

  // ── Render: main view ──────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="shrink-0 flex items-center gap-1 px-4 py-2 border-b border-border">
        {(
          [
            { id: 'recibidos', label: 'Recibidos', Icon: Inbox },
            { id: 'enviados', label: 'Enviados', Icon: Send },
            { id: 'redactar', label: 'Redactar', Icon: PenSquare },
          ] as const
        ).map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors cursor-pointer',
              activeTab === id
                ? 'bg-accent text-foreground font-medium'
                : 'text-muted-foreground hover:text-foreground hover:bg-accent/50',
            )}
          >
            <Icon className="size-3.5" />
            {label}
          </button>
        ))}
        <div className="ml-auto">
          <button
            onClick={handleRefresh}
            aria-label="Refrescar"
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors cursor-pointer"
          >
            <RefreshCw className="size-3.5" />
          </button>
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {/* ── RECIBIDOS ──────────────────────────────────────────────── */}
        {activeTab === 'recibidos' && (
          <div>
            {loadingMessages ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="size-4 animate-spin text-muted-foreground" />
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 gap-2 text-muted-foreground">
                <Inbox className="size-8 opacity-20" />
                <p className="text-sm">No hay mensajes</p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {messages.map((msg, idx) => {
                  if (!msg.parsed) {
                    // Non-parseable line — show raw text, no data loss
                    return (
                      <div
                        key={idx}
                        className="px-4 py-3 font-mono text-xs text-muted-foreground break-all"
                      >
                        {msg.raw}
                      </div>
                    )
                  }

                  const p = msg.parsed
                  const prio = p.plazo ? plazoPriority(p.plazo) : null
                  const isBeingSubmitted = submittingStatus === p.id
                  const isPendingThis =
                    pendingInput?.lineId === p.id

                  return (
                    <div key={idx} className="px-4 py-3 space-y-1.5">
                      {/* Row header */}
                      <div className="flex items-start gap-2 flex-wrap">
                        {/* Closed / open indicator */}
                        {p.closed ? (
                          <CheckSquare2 className="size-3.5 mt-0.5 text-muted-foreground/40 shrink-0" />
                        ) : (
                          <Square className="size-3.5 mt-0.5 text-muted-foreground/40 shrink-0" />
                        )}

                        <TipoBadge tipo={p.tipo} />

                        {/* Sender */}
                        <span className="text-xs text-muted-foreground">
                          De: {p.id_parts.remitente}
                        </span>

                        {/* Plazo */}
                        {p.plazo && (
                          <span
                            className={cn(
                              'text-xs font-mono',
                              prio === 'overdue'
                                ? 'text-destructive font-semibold'
                                : prio === 'soon'
                                  ? 'text-amber-600 dark:text-amber-400'
                                  : 'text-muted-foreground',
                            )}
                          >
                            plazo {p.plazo}
                          </span>
                        )}

                        {/* ID (faint) */}
                        <span className="ml-auto text-[10px] text-muted-foreground/40 font-mono shrink-0">
                          {p.id}
                        </span>
                      </div>

                      {/* Body */}
                      <p className="text-sm leading-relaxed">{renderBody(p.body)}</p>

                      {/* Reply-to */}
                      {p.reply_to && (
                        <p className="text-xs text-muted-foreground italic">
                          Respuesta a: {p.reply_to}
                        </p>
                      )}

                      {/* Estados */}
                      {p.estados.length > 0 && (
                        <div className="flex flex-wrap gap-1 pt-0.5">
                          {p.estados.map((e, i) => (
                            <span
                              key={i}
                              className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] bg-muted text-muted-foreground"
                            >
                              {e}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Status action buttons — only for open lines in my inbox */}
                      {!p.closed && (
                        <div className="flex flex-wrap items-center gap-1 pt-1">
                          {isBeingSubmitted ? (
                            <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
                          ) : (
                            <>
                              <ActionButton
                                label="Visto"
                                onClick={() => handleVisto(p.id, myInbox.doc_id)}
                              />
                              <ActionButton
                                label="Aceptado"
                                active={
                                  isPendingThis && pendingInput?.action === 'aceptado'
                                }
                                onClick={() =>
                                  handleInputAction(p.id, myInbox.doc_id, 'aceptado')
                                }
                              />
                              <ActionButton
                                label="Hecho"
                                active={
                                  isPendingThis && pendingInput?.action === 'hecho'
                                }
                                onClick={() =>
                                  handleInputAction(p.id, myInbox.doc_id, 'hecho')
                                }
                              />
                              <ActionButton
                                label="Rechazado"
                                danger
                                active={
                                  isPendingThis && pendingInput?.action === 'rechazado'
                                }
                                onClick={() =>
                                  handleInputAction(p.id, myInbox.doc_id, 'rechazado')
                                }
                              />
                              <ActionButton
                                label="Cerrar"
                                onClick={() => handleCerrar(p.id, myInbox.doc_id)}
                              />
                            </>
                          )}
                        </div>
                      )}

                      {/* Inline text input for actions that require it */}
                      {isPendingThis && pendingInput && (
                        <div className="flex items-center gap-2 pt-1">
                          <input
                            type="text"
                            value={pendingInput.text}
                            onChange={(e) =>
                              setPendingInput((prev) =>
                                prev ? { ...prev, text: e.target.value } : null,
                              )
                            }
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') void confirmInputAction()
                              if (e.key === 'Escape') setPendingInput(null)
                            }}
                            placeholder={
                              pendingInput.action === 'aceptado'
                                ? 'Nota o enlace (aceptado → …)'
                                : pendingInput.action === 'hecho'
                                  ? 'URL o fecha DD/MM (hecho → …)'
                                  : 'Motivo (rechazado: …)'
                            }
                            autoFocus
                            className="flex-1 min-w-0 rounded-md border border-border bg-background px-2.5 py-1 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                          />
                          <button
                            onClick={() => void confirmInputAction()}
                            className="shrink-0 px-2.5 py-1 text-xs rounded-md bg-foreground text-background hover:opacity-90 transition-opacity cursor-pointer"
                          >
                            OK
                          </button>
                          <button
                            onClick={() => setPendingInput(null)}
                            aria-label="Cancelar"
                            className="shrink-0 p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors cursor-pointer"
                          >
                            <X className="size-3.5" />
                          </button>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* ── ENVIADOS ──────────────────────────────────────────────── */}
        {activeTab === 'enviados' && (
          <div>
            {loadingSent ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="size-4 animate-spin text-muted-foreground" />
              </div>
            ) : sent.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 gap-2 text-muted-foreground">
                <Send className="size-8 opacity-20" />
                <p className="text-sm">No has enviado mensajes</p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {sent.map((item, idx) => {
                  if (!item.parsed) {
                    return (
                      <div
                        key={idx}
                        className="px-4 py-3 font-mono text-xs text-muted-foreground break-all"
                      >
                        {item.raw}
                      </div>
                    )
                  }

                  const p = item.parsed
                  const prio = p.plazo ? plazoPriority(p.plazo) : null

                  return (
                    <div key={idx} className="px-4 py-3 space-y-1.5">
                      <div className="flex items-start gap-2 flex-wrap">
                        {p.closed ? (
                          <CheckSquare2 className="size-3.5 mt-0.5 text-muted-foreground/40 shrink-0" />
                        ) : (
                          <Square className="size-3.5 mt-0.5 text-muted-foreground/40 shrink-0" />
                        )}
                        <TipoBadge tipo={p.tipo} />
                        <span className="text-xs text-muted-foreground">
                          Para:{' '}
                          <span className="font-medium text-foreground">
                            {item.inbox.display}
                          </span>
                        </span>
                        {p.plazo && (
                          <span
                            className={cn(
                              'text-xs font-mono',
                              prio === 'overdue'
                                ? 'text-destructive font-semibold'
                                : prio === 'soon'
                                  ? 'text-amber-600 dark:text-amber-400'
                                  : 'text-muted-foreground',
                            )}
                          >
                            plazo {p.plazo}
                          </span>
                        )}
                        <span className="ml-auto text-[10px] text-muted-foreground/40 font-mono shrink-0">
                          {p.id}
                        </span>
                      </div>

                      <p className="text-sm leading-relaxed">{renderBody(p.body)}</p>

                      {p.estados.length > 0 && (
                        <div className="flex flex-wrap gap-1 pt-0.5">
                          {p.estados.map((e, i) => (
                            <span
                              key={i}
                              className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] bg-muted text-muted-foreground"
                            >
                              {e}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* ── REDACTAR ──────────────────────────────────────────────── */}
        {activeTab === 'redactar' && (
          <div className="p-4 space-y-4 max-w-xl">
            {/* Confirmation: last sent line from server */}
            {lastSentLine && (
              <div className="rounded-md bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 p-3">
                <p className="text-xs text-green-700 dark:text-green-400 font-medium mb-1">
                  Último enviado (línea confirmada por el servidor)
                </p>
                <code className="block text-[11px] font-mono break-all text-green-800 dark:text-green-300">
                  {lastSentLine}
                </code>
              </div>
            )}

            {/* Recipient */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="buzon-recipient">
                Destinatario
              </label>
              <select
                id="buzon-recipient"
                value={recipientDocId}
                onChange={(e) => setRecipientDocId(e.target.value)}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="">Seleccionar buzón…</option>
                {inboxes.map((inbox) => (
                  <option key={inbox.doc_id} value={inbox.doc_id}>
                    {inbox.display} ({inbox.email})
                  </option>
                ))}
              </select>
            </div>

            {/* Tipo */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="buzon-tipo">
                Tipo
              </label>
              <select
                id="buzon-tipo"
                value={tipo}
                onChange={(e) => setTipo(e.target.value as Tipo)}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {TIPOS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>

            {/* Plazo (optional) */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="buzon-plazo">
                Plazo{' '}
                <span className="text-muted-foreground font-normal">(opcional, DD/MM)</span>
              </label>
              <input
                id="buzon-plazo"
                type="text"
                value={plazo}
                onChange={(e) => setPlazo(e.target.value)}
                placeholder="ej. 25/10"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>

            {/* Reply-to (optional) */}
            {tipo === 'Respuesta' && (
              <div className="space-y-1.5">
                <label className="text-sm font-medium" htmlFor="buzon-replyto">
                  Respuesta a (ID)
                </label>
                <input
                  id="buzon-replyto"
                  type="text"
                  value={replyTo}
                  onChange={(e) => setReplyTo(e.target.value)}
                  placeholder="ej. 20261021-1030-alice-bob"
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
            )}

            {/* Texto */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="buzon-texto">
                Mensaje
              </label>
              <textarea
                id="buzon-texto"
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                rows={3}
                placeholder="Escribe el texto del mensaje (sin saltos de línea)"
                className="w-full resize-none rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
            </div>

            {/* Links (optional) */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">
                  Enlaces{' '}
                  <span className="text-muted-foreground font-normal">(opcionales)</span>
                </span>
                <button
                  type="button"
                  onClick={handleAddEnlace}
                  className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                >
                  <Plus className="size-3" />
                  Añadir
                </button>
              </div>
              {enlaces.map((enlace, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={enlace.label}
                    onChange={(e) => handleEnlaceChange(idx, 'label', e.target.value)}
                    placeholder="Etiqueta"
                    className="flex-1 min-w-0 rounded-md border border-border bg-background px-2.5 py-1.5 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                  <input
                    type="url"
                    value={enlace.url}
                    onChange={(e) => handleEnlaceChange(idx, 'url', e.target.value)}
                    placeholder="https://…"
                    className="flex-1 min-w-0 rounded-md border border-border bg-background px-2.5 py-1.5 text-xs placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                  />
                  <button
                    type="button"
                    onClick={() => handleRemoveEnlace(idx)}
                    aria-label="Eliminar enlace"
                    className="shrink-0 p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors cursor-pointer"
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
              ))}
            </div>

            {/* Preview toggle + preview block */}
            <div className="space-y-2">
              <button
                type="button"
                onClick={() => setShowPreview((v) => !v)}
                disabled={!previewLine}
                className="text-xs text-muted-foreground hover:text-foreground disabled:opacity-40 transition-colors cursor-pointer"
              >
                {showPreview ? 'Ocultar previsualización' : 'Ver previsualización'}
              </button>
              {showPreview && previewLine && (
                <div className="rounded-md border border-border bg-muted/30 p-3">
                  <p className="text-[10px] text-muted-foreground mb-1">
                    Previsualización cliente — la línea definitiva la confirma el
                    servidor. El slug real sustituye a "yo" y "destinatario".
                  </p>
                  <code className="block text-[11px] font-mono break-all">
                    {previewLine}
                  </code>
                </div>
              )}
            </div>

            {/* Send button */}
            <div className="flex justify-end pt-2">
              <button
                onClick={() => void handleSend()}
                disabled={sending || !recipientDocId || !texto.trim()}
                className="inline-flex items-center gap-2 rounded-md bg-foreground text-background px-4 py-2 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50 cursor-pointer"
              >
                {sending ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Send className="size-3.5" />
                )}
                Enviar
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── ActionButton helper ────────────────────────────────────────────────────────

interface ActionButtonProps {
  label: string
  onClick: () => void
  active?: boolean
  danger?: boolean
}

function ActionButton({ label, onClick, active = false, danger = false }: ActionButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center rounded px-2 py-0.5 text-[11px] border transition-colors cursor-pointer',
        danger
          ? active
            ? 'bg-destructive/10 border-destructive/30 text-destructive'
            : 'border-border text-muted-foreground hover:border-destructive/50 hover:text-destructive'
          : active
            ? 'bg-accent border-border text-foreground'
            : 'border-border text-muted-foreground hover:text-foreground hover:bg-accent',
      )}
    >
      {label}
    </button>
  )
}
