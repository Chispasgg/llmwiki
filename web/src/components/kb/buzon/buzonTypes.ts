/**
 * Tipos de dominio del módulo buzón.
 * Exportados aquí para ser compartidos entre BuzonList (BL-003), el lector
 * (BL-004) y, en BL-006, BuzonView (que pasará a importarlos desde aquí
 * y eliminará sus definiciones inline).
 */

export interface InboxItem {
  doc_id: string
  path: string
  filename: string
  display: string
  email: string
  is_mine: boolean
}

export interface IdParts {
  fecha: string
  hora: string
  remitente: string
  destinatario: string | null
  b: boolean
}

export interface ParsedMessage {
  closed: boolean
  id: string
  id_parts: IdParts
  tipo: 'Mensaje' | 'Tarea' | 'Pendiente' | 'Respuesta' | null
  reply_to: string | null
  plazo: string | null
  body: string
  estados: string[]
}

export interface MessageLine {
  line_index: number
  raw: string
  parsed: ParsedMessage | null
}

export interface SentItem {
  inbox: { doc_id: string; display: string; email: string }
  raw: string
  parsed: (ParsedMessage & { remitente_slug?: string }) | null
}

export type Tipo = 'Mensaje' | 'Tarea' | 'Pendiente' | 'Respuesta'
