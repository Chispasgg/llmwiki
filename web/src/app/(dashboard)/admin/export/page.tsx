'use client'

import * as React from 'react'
import { Upload, Trash2, FileText, FileType } from 'lucide-react'
import { toast } from 'sonner'
import { API_URL, API_CREDENTIALS } from '@/lib/api'

interface TemplateInfo {
  type: string
  filename: string
  size_bytes: number
  updated_at: string
}

const TEMPLATE_META = {
  latex: {
    label: 'Plantilla LaTeX (PDF)',
    description: 'Controla el diseño del PDF: fuentes, márgenes, cabeceras y estilos.',
    accept: '.tex',
    icon: FileText,
  },
  reference_doc: {
    label: 'Documento de referencia (DOCX / ODT)',
    description: 'Define los estilos de Word/LibreOffice aplicados al exportar en formato office.',
    accept: '.docx,.odt',
    icon: FileType,
  },
}

export default function ExportTemplatesPage() {
  const [templates, setTemplates] = React.useState<TemplateInfo[]>([])
  const [loading, setLoading] = React.useState(true)
  const [uploading, setUploading] = React.useState<string | null>(null)
  const [deleting, setDeleting] = React.useState<string | null>(null)

  const fetchTemplates = React.useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/v1/superadmin/export-templates`, {
        credentials: API_CREDENTIALS,
      })
      if (!res.ok) throw new Error()
      setTemplates(await res.json())
    } catch {
      toast.error('Error al cargar las plantillas')
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => { fetchTemplates() }, [fetchTemplates])

  const handleUpload = async (type: string, file: File) => {
    setUploading(type)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${API_URL}/v1/superadmin/export-templates/${type}`, {
        method: 'POST',
        credentials: API_CREDENTIALS,
        body: form,
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({})) as { detail?: string }
        toast.error(typeof err.detail === 'string' ? err.detail : 'Error al subir la plantilla')
        return
      }
      toast.success('Plantilla actualizada')
      await fetchTemplates()
    } catch {
      toast.error('Error al subir la plantilla')
    } finally {
      setUploading(null)
    }
  }

  const handleDelete = async (type: string) => {
    setDeleting(type)
    try {
      const res = await fetch(`${API_URL}/v1/superadmin/export-templates/${type}`, {
        method: 'DELETE',
        credentials: API_CREDENTIALS,
      })
      if (!res.ok) { toast.error('Error al eliminar la plantilla'); return }
      toast.success('Plantilla eliminada — se usará la plantilla por defecto')
      await fetchTemplates()
    } catch {
      toast.error('Error al eliminar la plantilla')
    } finally {
      setDeleting(null)
    }
  }

  if (loading) {
    return <div className="text-sm text-muted-foreground">Cargando…</div>
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Plantillas de exportación</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Personaliza los estilos de los documentos exportados. Si no hay plantilla custom, se usa la plantilla por defecto incluida en el sistema.
        </p>
      </div>

      {(Object.entries(TEMPLATE_META) as [string, typeof TEMPLATE_META.latex][]).map(([type, meta]) => {
        const active = templates.find((t) => t.type === type)
        const Icon = meta.icon
        const isUploading = uploading === type
        const isDeleting = deleting === type

        return (
          <div key={type} className="border border-border rounded-lg p-5 space-y-4">
            <div className="flex items-start gap-3">
              <Icon className="size-5 text-muted-foreground mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="font-medium text-sm">{meta.label}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{meta.description}</p>
              </div>
            </div>

            {active ? (
              <div className="bg-muted/50 rounded-md px-3 py-2 text-xs space-y-0.5">
                <p className="font-medium text-foreground">Plantilla custom activa</p>
                <p className="text-muted-foreground">
                  {active.filename} · {(active.size_bytes / 1024).toFixed(1)} KB
                </p>
                <p className="text-muted-foreground">
                  Actualizada: {new Date(active.updated_at).toLocaleString('es-ES')}
                </p>
              </div>
            ) : (
              <div className="bg-muted/30 rounded-md px-3 py-2 text-xs text-muted-foreground">
                Usando plantilla por defecto del sistema
              </div>
            )}

            <div className="flex gap-2">
              <label
                className={`flex items-center gap-2 px-3 py-1.5 text-xs border border-border rounded-md transition-colors ${isUploading ? 'opacity-50 cursor-not-allowed' : 'hover:bg-accent cursor-pointer'}`}
              >
                <Upload className="size-3.5" />
                {isUploading ? 'Subiendo…' : active ? 'Reemplazar' : 'Subir plantilla'}
                <input
                  type="file"
                  accept={meta.accept}
                  className="sr-only"
                  disabled={isUploading}
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (file) handleUpload(type, file)
                    e.target.value = ''
                  }}
                />
              </label>
              {active && (
                <button
                  onClick={() => handleDelete(type)}
                  disabled={isDeleting}
                  className="flex items-center gap-2 px-3 py-1.5 text-xs text-destructive border border-destructive/30 rounded-md hover:bg-destructive/10 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Trash2 className="size-3.5" />
                  {isDeleting ? 'Eliminando…' : 'Eliminar'}
                </button>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
