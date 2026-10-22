/**
 * Helpers puros de renderizado del módulo buzón.
 * Exportados aquí para ser compartidos entre BuzonView (BL-006), BuzonCompose (BL-005)
 * y BuzonReader (BL-004).
 */

import * as React from 'react'
import { ExternalLink } from 'lucide-react'
import type { Tipo } from './buzonTypes'

// ── buildPreviewLine ──────────────────────────────────────────────────────────

/**
 * Client-side preview of a buzón line.
 * Uses "yo" as sender slug (not known client-side) and "destinatario" as placeholder.
 * The server will produce the real line with correct slugs.
 */
export function buildPreviewLine(opts: {
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

// ── renderBody ────────────────────────────────────────────────────────────────

/** Render a body string with markdown-style [label](url) links.
 *
 * Only renders an <a> when the URL starts with http:// or https://.
 * Any other scheme (javascript:, data:, vbscript:, …) is rendered as
 * plain text — clicking a non-http/s URL could execute stored XSS.
 */
export function renderBody(body: string): React.ReactNode {
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

// ── refKind ───────────────────────────────────────────────────────────────────

export type RefKind = 'jira' | 'mr' | 'wiki' | 'link'

/**
 * Clasifica el tipo de referencia de una URL por heurística.
 * - Contiene `/browse/`, `atlassian` o `jira` → 'jira'
 * - Contiene `/-/merge_requests/`             → 'mr'
 * - Contiene `/wiki/`                         → 'wiki'
 * - En otro caso                              → 'link'
 */
export function refKind(url: string): RefKind {
  if (/\/browse\/|atlassian|jira/i.test(url)) return 'jira'
  if (/\/-\/merge_requests\//i.test(url)) return 'mr'
  if (/\/wiki\//i.test(url)) return 'wiki'
  return 'link'
}

// ── extractLinks ──────────────────────────────────────────────────────────────

export interface LinkRef {
  label: string
  url: string
}

/**
 * Extrae los enlaces markdown `[label](url)` con esquema http(s) del cuerpo.
 * Cualquier otro esquema (javascript:, data:, vbscript:, …) se ignora
 * para evitar que se rendericen como enlaces clicables.
 */
export function extractLinks(body: string): LinkRef[] {
  const LINK_RE = /\[([^\]]+)\]\(([^)]+)\)/g
  const results: LinkRef[] = []
  let match: RegExpExecArray | null

  while ((match = LINK_RE.exec(body)) !== null) {
    const url = match[2]
    // Solo http(s) — mismo criterio que renderBody
    if (/^https?:\/\//i.test(url)) {
      results.push({ label: match[1], url })
    }
  }

  return results
}
