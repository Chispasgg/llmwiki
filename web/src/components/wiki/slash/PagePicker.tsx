'use client'

import * as React from 'react'
import { Search, X } from 'lucide-react'
import type { DocumentListItem } from '@/lib/types'

interface PagePickerProps {
  open: boolean
  /** All documents available for this KB (will be filtered to wiki .md pages). */
  documents: DocumentListItem[]
  onSelect: (doc: DocumentListItem) => void
  onClose: () => void
}

/**
 * Modal picker for internal wiki pages.
 *
 * Filters the supplied documents to wiki markdown files, lets the user search
 * by title or filename, and reports the selected document back to the caller.
 * The caller is responsible for inserting the actual link into the editor.
 */
export function PagePicker({ open, documents, onSelect, onClose }: PagePickerProps) {
  const [query, setQuery] = React.useState('')
  const inputRef = React.useRef<HTMLInputElement>(null)

  // Focus search input when the picker opens.
  React.useEffect(() => {
    if (open) {
      setQuery('')
      const id = window.setTimeout(() => inputRef.current?.focus(), 40)
      return () => window.clearTimeout(id)
    }
  }, [open])

  // Only show wiki markdown documents.
  const wikiDocs = React.useMemo(
    () =>
      documents.filter(
        (d) =>
          (d.path === '/wiki/' || d.path.startsWith('/wiki/')) &&
          d.file_type === 'md' &&
          !d.archived,
      ),
    [documents],
  )

  const filtered = React.useMemo(() => {
    if (!query) return wikiDocs
    const q = query.toLowerCase()
    return wikiDocs.filter(
      (d) =>
        (d.title ?? '').toLowerCase().includes(q) ||
        d.filename.toLowerCase().includes(q),
    )
  }, [wikiDocs, query])

  if (!open) return null

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/70 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="bg-popover border border-border rounded-xl shadow-xl w-full max-w-md overflow-hidden">
        {/* Search header */}
        <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
          <Search className="size-4 text-muted-foreground shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search wiki pages…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            onKeyDown={(e) => {
              if (e.key === 'Escape') onClose()
            }}
          />
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            aria-label="Close"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Results list */}
        <div className="overflow-y-auto max-h-72">
          {filtered.length === 0 ? (
            <p className="px-4 py-8 text-sm text-muted-foreground text-center">
              No pages found
            </p>
          ) : (
            filtered.map((doc) => {
              const title = doc.title || doc.filename.replace(/\.(md|txt)$/, '')
              const path = (doc.path + doc.filename).replace(/^\/wiki\/?/, '')
              return (
                <button
                  key={doc.id}
                  // onMouseDown so we don't lose editor focus before inserting.
                  onMouseDown={(e) => {
                    e.preventDefault()
                    onSelect(doc)
                  }}
                  className="w-full flex flex-col gap-0.5 px-4 py-2.5 text-left hover:bg-accent transition-colors cursor-pointer"
                >
                  <span className="text-sm font-medium text-foreground truncate">
                    {title}
                  </span>
                  <span className="text-xs text-muted-foreground truncate">{path}</span>
                </button>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
