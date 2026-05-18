'use client'

import * as React from 'react'
import { Loader2, Square, CheckSquare, MinusSquare } from 'lucide-react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import type { WikiNode } from '@/lib/types'

// ── Helpers ────────────────────────────────────────────────────────────────

function collectLeafDocIds(nodes: WikiNode[]): string[] {
  const result: string[] = []
  const traverse = (n: WikiNode) => {
    if (n.docId != null && n.path) result.push(n.docId)
    n.children?.forEach(traverse)
  }
  nodes.forEach(traverse)
  return result
}

function getDescendantDocIds(node: WikiNode): string[] {
  const result: string[] = []
  const traverse = (n: WikiNode) => {
    if (n.docId != null && n.path) result.push(n.docId)
    n.children?.forEach(traverse)
  }
  traverse(node)
  return result
}

type CheckState = 'checked' | 'indeterminate' | 'unchecked'

function nodeCheckState(node: WikiNode, selected: Set<string>): CheckState {
  const hasChildren = !!node.children?.length
  if (!hasChildren) {
    if (node.docId != null && node.path) {
      return selected.has(node.docId) ? 'checked' : 'unchecked'
    }
    return 'unchecked'
  }
  const descendants = getDescendantDocIds(node)
  if (descendants.length === 0) return 'unchecked'
  const n = descendants.filter((d) => selected.has(d)).length
  if (n === 0) return 'unchecked'
  if (n === descendants.length) return 'checked'
  return 'indeterminate'
}

// ── Format selector ─────────────────────────────────────────────────────────

type ExportFormat = 'pdf' | 'docx' | 'odt'

const FORMAT_LABELS: Record<ExportFormat, string> = {
  pdf: 'PDF',
  docx: 'Word (DOCX)',
  odt: 'LibreOffice (ODT)',
}

// ── Public component ────────────────────────────────────────────────────────

interface ExportPdfDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  kbName: string
  wikiTree: WikiNode[]
  onExport: (docIds: string[], format: ExportFormat) => void
  loading: boolean
}

export function ExportPdfDialog({
  open, onOpenChange, kbName, wikiTree, onExport, loading,
}: ExportPdfDialogProps) {
  const allDocIds = React.useMemo(() => collectLeafDocIds(wikiTree), [wikiTree])
  const [selected, setSelected] = React.useState<Set<string>>(() => new Set(allDocIds))
  const [format, setFormat] = React.useState<ExportFormat>('pdf')

  React.useEffect(() => {
    if (open) setSelected(new Set(allDocIds))
  }, [open, allDocIds])

  const toggleLeaf = React.useCallback((docId: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(docId)) next.delete(docId)
      else next.add(docId)
      return next
    })
  }, [])

  const toggleNode = React.useCallback((node: WikiNode) => {
    const descendants = getDescendantDocIds(node)
    setSelected((prev) => {
      const state = nodeCheckState(node, prev)
      const next = new Set(prev)
      if (state === 'checked') descendants.forEach((d) => next.delete(d))
      else descendants.forEach((d) => next.add(d))
      return next
    })
  }, [])

  const handleExport = () => onExport(Array.from(selected), format)

  return (
    <Dialog open={open} onOpenChange={loading ? undefined : onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle className="text-base">Exportar wiki</DialogTitle>
        </DialogHeader>

        {/* Selector de formato */}
        <div className="flex gap-2">
          {(Object.keys(FORMAT_LABELS) as ExportFormat[]).map((fmt) => (
            <button
              key={fmt}
              onClick={() => setFormat(fmt)}
              className={cn(
                'flex-1 px-3 py-1.5 text-xs rounded-md border transition-colors cursor-pointer',
                format === fmt
                  ? 'border-primary bg-primary/10 text-primary font-medium'
                  : 'border-border text-muted-foreground hover:text-foreground hover:bg-accent',
              )}
            >
              {FORMAT_LABELS[fmt]}
            </button>
          ))}
        </div>

        {/* Contador + acciones rápidas */}
        <div className="flex items-center justify-between px-0.5">
          <span className="text-xs text-muted-foreground">
            {selected.size} de {allDocIds.length} páginas
          </span>
          <div className="flex gap-3">
            <button
              onClick={() => setSelected(new Set(allDocIds))}
              className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2 transition-colors cursor-pointer"
            >
              Todo
            </button>
            <button
              onClick={() => setSelected(new Set())}
              className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2 transition-colors cursor-pointer"
            >
              Ninguno
            </button>
          </div>
        </div>

        {/* Árbol de selección */}
        <div className="overflow-y-auto max-h-64 border border-border rounded-md px-1 py-1">
          {wikiTree.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-4">No hay páginas en este wiki.</p>
          ) : (
            wikiTree.map((node, i) => (
              <TreeNodeRow
                key={node.path ?? node.title ?? i}
                node={node}
                depth={0}
                selected={selected}
                onToggleLeaf={toggleLeaf}
                onToggleNode={toggleNode}
              />
            ))
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <button
            onClick={() => onOpenChange(false)}
            disabled={loading}
            className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground border border-border rounded-md hover:bg-accent transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancelar
          </button>
          <button
            onClick={handleExport}
            disabled={selected.size === 0 || loading}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading && <Loader2 className="size-3.5 animate-spin" />}
            {loading ? 'Generando…' : `Generar ${FORMAT_LABELS[format]} (${selected.size})`}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Internal: checkbox visual ───────────────────────────────────────────────

function CheckIcon({ state }: { state: CheckState }) {
  if (state === 'checked') return <CheckSquare className="size-3.5 text-primary shrink-0" />
  if (state === 'indeterminate') return <MinusSquare className="size-3.5 text-primary/50 shrink-0" />
  return <Square className="size-3.5 text-muted-foreground/30 shrink-0" />
}

// ── Internal: tree row ──────────────────────────────────────────────────────

function TreeNodeRow({
  node, depth, selected, onToggleLeaf, onToggleNode,
}: {
  node: WikiNode
  depth: number
  selected: Set<string>
  onToggleLeaf: (id: string) => void
  onToggleNode: (n: WikiNode) => void
}) {
  const hasChildren = !!node.children?.length
  const isLeaf = !hasChildren && node.path != null && node.docId != null
  const checkState = nodeCheckState(node, selected)

  const handleClick = () => {
    if (isLeaf && node.docId != null) onToggleLeaf(node.docId)
    else onToggleNode(node)
  }

  return (
    <div>
      <button
        onClick={handleClick}
        className={cn(
          'flex items-center gap-2 w-full text-left text-[13px] rounded-md py-1.5 hover:bg-accent/50 transition-colors cursor-pointer',
          checkState === 'unchecked' ? 'text-muted-foreground' : 'text-foreground',
        )}
        style={{ paddingLeft: `${depth * 14 + 8}px`, paddingRight: '8px' }}
      >
        <CheckIcon state={checkState} />
        <span className="truncate flex-1">{node.title}</span>
      </button>
      {hasChildren && node.children!.map((child, i) => (
        <TreeNodeRow
          key={child.path ?? child.title ?? i}
          node={child}
          depth={depth + 1}
          selected={selected}
          onToggleLeaf={onToggleLeaf}
          onToggleNode={onToggleNode}
        />
      ))}
    </div>
  )
}
