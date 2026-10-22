'use client'

/**
 * BuzonView — vista nativa de buzón para una KB (modo hosted).
 *
 * Flujo principal:
 *  1. Carga todos los buzones de la KB (GET inboxes).
 *  2. Si no hay buzón propio → pantalla "Crear mi buzón".
 *  3. Si hay buzón → layout 2 paneles: lista | lector + sheet Redactar.
 *
 * Todas las llamadas a la API usan apiFetch, que ya incluye la cookie de sesión.
 * Los errores HTTP se muestran con toast (sonner).
 */

import * as React from 'react'
import { PenSquare, RefreshCw, Plus, Loader2, Mail } from 'lucide-react'
import { toast } from 'sonner'
import { apiFetch } from '@/lib/api'
import { cn } from '@/lib/utils'
import { buzonRootClass } from './buzonTheme'
import styles from './buzon.module.css'
import { BuzonList } from './BuzonList'
import type { BuzonRow } from './buzonListHelpers'
import { BuzonReader } from './BuzonReader'
import { BuzonCompose } from './BuzonCompose'
import type { ComposePayload } from './BuzonCompose'
import type { InboxItem, MessageLine, SentItem } from './buzonTypes'

// ── Pure helpers ──────────────────────────────────────────────────────────────

/** Fecha de hoy en formato DD/MM para los estados "visto DD/MM". */
function todayDDMM(): string {
  const d = new Date()
  return `${d.getDate()}/${d.getMonth() + 1}`
}

// ── BuzonView ─────────────────────────────────────────────────────────────────

export interface BuzonViewProps {
  kbId: string
}

type ActiveTab = 'recibidos' | 'enviados'

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
  const [activeTab, setActiveTab] = React.useState<ActiveTab>('recibidos')
  const [selectedId, setSelectedId] = React.useState<string | null>(null)

  function changeTab(tab: ActiveTab) {
    setActiveTab(tab)
    setSelectedId(null)
  }

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
  // submittingStatus: lineId que se está guardando (muestra spinner en ese mensaje)
  const [submittingStatus, setSubmittingStatus] = React.useState<string | null>(null)

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
        // Recargar para reflejar el nuevo estado
        if (myInbox) await loadMessages(myInbox.doc_id)
      } catch (err) {
        toast.error((err as Error).message || 'Error al actualizar estado')
      } finally {
        setSubmittingStatus(null)
      }
    },
    [kbId, myInbox, loadMessages],
  )

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

  // ── Redactar / Compose ────────────────────────────────────────────────────
  const [composeOpen, setComposeOpen] = React.useState(false)
  const [sending, setSending] = React.useState(false)

  const handleSendPayload = async (payload: ComposePayload) => {
    if (!payload.recipient_doc_id) {
      toast.error('Selecciona un destinatario')
      return
    }
    if (!payload.texto.trim()) {
      toast.error('Escribe el texto del mensaje')
      return
    }
    setSending(true)
    try {
      await apiFetch<{ line: string; ok: boolean }>(
        `/v1/knowledge-bases/${kbId}/buzon/send`,
        {
          method: 'POST',
          body: JSON.stringify({
            recipient_doc_id: payload.recipient_doc_id,
            tipo: payload.tipo,
            texto: payload.texto,
            plazo: payload.plazo,
            reply_to: payload.reply_to,
            enlaces: payload.enlaces,
          }),
        },
      )
      toast.success('Mensaje enviado')
      setComposeOpen(false)
      changeTab('enviados')
      void loadSent()
    } catch (err) {
      toast.error((err as Error).message || 'Error al enviar')
    } finally {
      setSending(false)
    }
  }

  // ── Refresh ────────────────────────────────────────────────────────────────
  const handleRefresh = () => {
    if (activeTab === 'recibidos' && myInbox) void loadMessages(myInbox.doc_id)
    if (activeTab === 'enviados') void loadSent()
  }

  // ── Rows para BuzonList ────────────────────────────────────────────────────

  const receivedRows: BuzonRow[] = messages.map((line) => ({
    key: String(line.line_index),
    id: line.parsed?.id ?? null,
    who: line.parsed?.id_parts.remitente ?? '—',
    parsed: line.parsed,
    raw: line.raw,
  }))

  const sentRows: BuzonRow[] = sent.map((item, idx) => ({
    key: String(idx),
    id: item.parsed?.id ?? null,
    who: item.inbox.display,
    parsed: item.parsed,
    raw: item.raw,
  }))

  const activeRows = activeTab === 'recibidos' ? receivedRows : sentRows

  // ── Selected row (para BuzonReader) ────────────────────────────────────────
  const selectedRow: BuzonRow | null =
    selectedId !== null ? (activeRows.find((r) => r.id === selectedId) ?? null) : null

  // ── Render: cargando ──────────────────────────────────────────────────────

  if (loadingInboxes) {
    return (
      <div className={cn(buzonRootClass, styles['view-center'])}>
        <Loader2 className="size-5 animate-spin opacity-40" />
      </div>
    )
  }

  // ── Render: sin buzón propio ───────────────────────────────────────────────

  if (!myInbox) {
    return (
      <div className={cn(buzonRootClass, styles['view-center'])}>
        <Mail className="size-10 opacity-20" />
        <div>
          <h3 className="mb-1.5 text-[15px] font-medium">Sin buzón propio</h3>
          <p className="text-sm opacity-60 leading-relaxed">
            Crea tu buzón para poder recibir y enviar mensajes en esta KB.
          </p>
        </div>
        <button
          onClick={() => void handleCreateInbox()}
          disabled={creatingInbox}
          className={cn(styles.btn, styles.primary)}
        >
          {creatingInbox ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Plus size={14} />
          )}
          Crear mi buzón
        </button>
      </div>
    )
  }

  // ── Render: vista principal (2 paneles) ────────────────────────────────────

  return (
    <div className={cn(buzonRootClass, 'h-full')}>
      <div className={styles.wrap}>

        {/* Barra superior */}
        <div className={styles.topbar}>
          <h1>Buzón</h1>
          <div className={styles.tabs}>
            {(['recibidos', 'enviados'] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                className={styles.tab}
                aria-selected={activeTab === tab}
                onClick={() => changeTab(tab)}
              >
                {tab === 'recibidos' ? 'Recibidos' : 'Enviados'}
              </button>
            ))}
          </div>
          <div className={styles.spacer} />
          <button
            type="button"
            className={cn(styles.btn, styles.primary)}
            onClick={() => setComposeOpen(true)}
          >
            <PenSquare size={14} />
            Redactar
          </button>
          <button
            type="button"
            className={styles.iconbtn}
            onClick={handleRefresh}
            aria-label="Refrescar"
          >
            <RefreshCw size={14} />
          </button>
        </div>

        {/* Shell de 2 paneles: lista | lector */}
        <div className={styles.shell2}>

          {/* Columna izquierda: lista */}
          <BuzonList
            rows={activeRows}
            selectedId={selectedId}
            onSelect={setSelectedId}
            loading={activeTab === 'recibidos' ? loadingMessages : loadingSent}
            emptyText={
              activeTab === 'recibidos' ? 'No hay mensajes' : 'No has enviado mensajes'
            }
          />

          {/* Columna derecha: lector */}
          <BuzonReader
            row={selectedRow}
            emptyText="Selecciona un mensaje"
            actions={
              // Las acciones solo aplican a mensajes recibidos, abiertos y de mi buzón
              activeTab === 'recibidos' &&
              selectedRow?.parsed != null &&
              !selectedRow.parsed.closed &&
              myInbox != null
                ? {
                    submitting: submittingStatus === selectedId,

                    onVisto: () => {
                      if (!selectedId) return
                      void submitStatus({
                        lineId: selectedId,
                        buzonDocId: myInbox.doc_id,
                        estado: `visto ${todayDDMM()}`,
                      })
                    },

                    onAccept: (text: string) => {
                      if (!selectedId) return
                      // Eliminar saltos de línea: texto pegado multilínea produciría
                      // un estado malformado y un 400 opaco del backend.
                      const clean = text.replace(/[\r\n]+/g, ' ').trim()
                      if (!clean) { toast.error('Escribe el texto…'); return }
                      void submitStatus({
                        lineId: selectedId,
                        buzonDocId: myInbox.doc_id,
                        estado: `aceptado → ${clean}`,
                      })
                    },

                    onDone: (text: string) => {
                      if (!selectedId) return
                      const clean = text.replace(/[\r\n]+/g, ' ').trim()
                      if (!clean) { toast.error('Escribe el texto…'); return }
                      // Formato DD/MM → "hecho DD/MM"; cualquier otro → "hecho → <texto>"
                      const isDate = /^\d{1,2}\/\d{1,2}$/.test(clean)
                      void submitStatus({
                        lineId: selectedId,
                        buzonDocId: myInbox.doc_id,
                        estado: isDate ? `hecho ${clean}` : `hecho → ${clean}`,
                      })
                    },

                    onReject: (text: string) => {
                      if (!selectedId) return
                      const clean = text.replace(/[\r\n]+/g, ' ').trim()
                      if (!clean) { toast.error('Escribe el texto…'); return }
                      void submitStatus({
                        lineId: selectedId,
                        buzonDocId: myInbox.doc_id,
                        estado: `rechazado: ${clean}`,
                      })
                    },

                    onClose: () => {
                      if (!selectedId) return
                      void submitStatus({
                        lineId: selectedId,
                        buzonDocId: myInbox.doc_id,
                        closed: true,
                      })
                    },
                  }
                : undefined
            }
          />
        </div>

        {/* Sheet de redactar */}
        <BuzonCompose
          open={composeOpen}
          onClose={() => setComposeOpen(false)}
          inboxes={inboxes}
          sending={sending}
          onSend={(payload) => void handleSendPayload(payload)}
        />

      </div>
    </div>
  )
}
