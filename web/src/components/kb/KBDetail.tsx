'use client'

import * as React from 'react'
import { useSearchParams } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import { Upload as UploadIcon, BookOpen, ArrowUpRight, Loader2, Menu } from 'lucide-react'
import * as tus from 'tus-js-client'
import { useUserStore, useKBStore, useNotificationsStore } from '@/stores'
import { useKBDocuments } from '@/hooks/useKBDocuments'
import { apiFetch } from '@/lib/api'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { KBSidenav } from '@/components/kb/KBSidenav'
import { FilesGrid } from '@/components/kb/FilesGrid'
import { GraphViewer } from '@/components/kb/GraphViewer'
import { SelectionActionBar } from '@/components/kb/SelectionActionBar'
import { WikiContent } from '@/components/wiki/WikiContent'
import type { BreadcrumbItem } from '@/components/wiki/WikiContent'
import type { DocumentListItem, WikiNode } from '@/lib/types'
import type { ViewMode } from '@/app/(dashboard)/wikis/[slug]/[[...path]]/page'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const SIDENAV_MIN = 180
const SIDENAV_MAX = 480
const SIDENAV_DEFAULT = 256
const SIDENAV_STORAGE_KEY = 'wiki_sidenav_width'


const naturalSort = (a: string, b: string) =>
  a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })

function buildTreeFromDocs(docs: DocumentListItem[]): WikiNode[] {
  const sorted = [...docs].sort((a, b) => {
    const orderDiff = (a.sort_order ?? 999) - (b.sort_order ?? 999)
    if (orderDiff !== 0) return orderDiff
    return naturalSort(a.filename || '', b.filename || '')
  })

  interface MutableNode {
    title: string
    path?: string
    docNumber?: number | null
    docId?: string | null
    children: Map<string, MutableNode>
  }

  const root = new Map<string, MutableNode>()

  for (const doc of sorted) {
    const relative = (doc.path + doc.filename).replace(/^\/wiki\/?/, '')
    const parts = relative.split('/').filter(Boolean)
    const title =
      doc.title ||
      parts[parts.length - 1].replace(/\.(md|txt|json)$/, '').replace(/[-_]/g, ' ')

    let level = root
    for (let i = 0; i < parts.length; i++) {
      const slug = parts[i].replace(/\.(md|txt|json)$/, '')
      const isLeaf = i === parts.length - 1

      if (isLeaf) {
        const existing = level.get(slug)
        if (existing) {
          // Folder node already created by a child — enrich it with doc info
          existing.path = relative
          existing.docNumber = doc.document_number ?? null
          existing.docId = doc.id
          existing.title = title
        } else {
          level.set(slug, {
            title,
            path: relative,
            docNumber: doc.document_number ?? null,
            docId: doc.id,
            children: new Map(),
          })
        }
      } else {
        if (!level.has(slug)) {
          const folderTitle = slug.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
          level.set(slug, { title: folderTitle, children: new Map() })
        }
        level = level.get(slug)!.children
      }
    }
  }

  function toWikiNodes(nodeMap: Map<string, MutableNode>, isRoot = false): WikiNode[] {
    const nodes = Array.from(nodeMap.values()).map((node) => ({
      title: node.title,
      path: node.path,
      docNumber: node.docNumber,
      docId: node.docId,
      children: node.children.size > 0 ? toWikiNodes(node.children) : undefined,
    }))

    if (isRoot) {
      nodes.sort((a, b) => {
        const sa = a.path?.replace(/\.(md|txt|json)$/, '').split('/')[0] ?? a.title.toLowerCase()
        const sb = b.path?.replace(/\.(md|txt|json)$/, '').split('/')[0] ?? b.title.toLowerCase()
        if (sa === 'overview') return -1
        if (sb === 'overview') return 1
        if (sa === 'log') return 1
        if (sb === 'log') return -1
        return naturalSort(a.title, b.title)
      })
    } else {
      nodes.sort((a, b) => naturalSort(a.title, b.title))
    }

    return nodes
  }

  return toWikiNodes(root, true)
}

function enrichTreeWithDocNumbers(tree: WikiNode[], docs: DocumentListItem[]): WikiNode[] {
  const pathToDoc = new Map<string, { docNumber: number | null; docId: string }>()
  for (const doc of docs) {
    const relative = (doc.path + doc.filename).replace(/^\/wiki\/?/, '')
    pathToDoc.set(relative, { docNumber: doc.document_number, docId: doc.id })
  }
  function enrich(nodes: WikiNode[]): WikiNode[] {
    return nodes.map((node) => ({
      ...node,
      docNumber: node.path ? (pathToDoc.get(node.path)?.docNumber ?? null) : null,
      docId: node.path ? (pathToDoc.get(node.path)?.docId ?? null) : null,
      children: node.children ? enrich(node.children) : undefined,
    }))
  }
  return enrich(tree)
}

function findFirstPath(nodes: WikiNode[]): { path: string; docNumber: number | null } | null {
  for (const node of nodes) {
    if (node.path) return { path: node.path, docNumber: node.docNumber ?? null }
    if (node.children) {
      const found = findFirstPath(node.children)
      if (found) return found
    }
  }
  return null
}

function buildBreadcrumbs(
  nodes: WikiNode[],
  activePath: string,
  wikiTitle: string,
): Array<{ title: string; path?: string; docNumber?: number | null }> | null {
  // Try to find the active node. Returns ancestor chain if found.
  function search(
    nodes: WikiNode[],
    path: string,
  ): Array<{ title: string; path?: string; docNumber?: number | null }> | null {
    for (const node of nodes) {
      if (node.path === path) {
        return [{ title: node.title, path: node.path, docNumber: node.docNumber }]
      }
      if (node.children) {
        const found = search(node.children, path)
        if (found) {
          return [{ title: node.title, path: node.path, docNumber: node.docNumber }, ...found]
        }
      }
    }
    return null
  }

  const chain = search(nodes, activePath)
  if (!chain) return null

  const firstNode = findFirstPath(nodes)
  const wikiCrumb = { title: wikiTitle, path: firstNode?.path, docNumber: firstNode?.docNumber }
  return [wikiCrumb, ...chain]
}

type Props = {
  kbId: string
  kbSlug: string
  kbName: string
  viewMode: ViewMode
  routeFilesPath: string
}

export function KBDetail({ kbId, kbSlug, kbName, viewMode, routeFilesPath }: Props) {
  const searchParams = useSearchParams()
  const userId = useUserStore((s) => s.user?.id)
  const workspaceSlug = useKBStore((s) => s.knowledgeBases.find((kb) => kb.id === kbId)?.workspace_slug ?? null)
  const workspaceName = useKBStore((s) => s.knowledgeBases.find((kb) => kb.id === kbId)?.workspace_name ?? null)
  const ownerName = useKBStore((s) => s.knowledgeBases.find((kb) => kb.id === kbId)?.owner_name ?? null)
  const markNotificationRead = useNotificationsStore((s) => s.markRead)
  React.useEffect(() => { markNotificationRead(kbId) }, [kbId, markNotificationRead])
  const { documents, setDocuments, loading } = useKBDocuments(kbId)
  const [sidenavOpen, setSidenavOpen] = React.useState(false)
  const [sidenavWidth, setSidenavWidth] = React.useState(SIDENAV_DEFAULT)
  const dragWidthRef = React.useRef(SIDENAV_DEFAULT)

  React.useEffect(() => {
    const stored = localStorage.getItem(SIDENAV_STORAGE_KEY)
    if (stored) {
      const n = parseInt(stored, 10)
      if (n >= SIDENAV_MIN && n <= SIDENAV_MAX) {
        setSidenavWidth(n)
        dragWidthRef.current = n
      }
    }
  }, [])

  const handleResizeMouseDown = React.useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    const startX = e.clientX
    const startWidth = dragWidthRef.current

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    const onMouseMove = (ev: MouseEvent) => {
      const newWidth = Math.min(SIDENAV_MAX, Math.max(SIDENAV_MIN, startWidth + ev.clientX - startX))
      dragWidthRef.current = newWidth
      setSidenavWidth(newWidth)
    }

    const onMouseUp = () => {
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      localStorage.setItem(SIDENAV_STORAGE_KEY, String(dragWidthRef.current))
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }

    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
  }, [])

  // ─── URL helpers ─────────────────────────────────────────────
  // Search param updates are instant (no Next.js route recompilation).
  // Path changes only happen on view-mode switches (rare).

  const updateParam = React.useCallback((key: string, value: string | null) => {
    const url = new URL(window.location.href)
    if (value != null) url.searchParams.set(key, value)
    else url.searchParams.delete(key)
    window.history.replaceState(window.history.state, '', url.pathname + url.search)
  }, [])

  const navigateToView = React.useCallback((view: ViewMode, opts?: { filesPath?: string; searchParams?: Record<string, string> }) => {
    let url = `/wikis/${kbSlug}`
    if (view === 'files') {
      const path = opts?.filesPath ?? '/'
      const clean = path === '/' ? '' : path.replace(/^\//, '').replace(/\/$/, '')
      url += clean ? `/files/${encodeURI(clean)}` : '/files'
    } else if (view === 'graph') {
      url += '/graph'
    }
    if (opts?.searchParams) {
      const sp = new URLSearchParams(opts.searchParams)
      url += '?' + sp.toString()
    }
    window.history.pushState(window.history.state, '', url)
  }, [kbSlug])

  // ─── Document splits ─────────────────────────────────────────
  const wikiDocs = React.useMemo(
    () => documents.filter((d) => (d.path === '/wiki/' || d.path.startsWith('/wiki/')) && !d.archived && d.file_type === 'md'),
    [documents],
  )
  const sourceDocs = React.useMemo(
    () => documents.filter((d) => !d.path.startsWith('/wiki/') && !d.archived),
    [documents],
  )

  // ─── View state ──────────────────────────────────────────────
  // activeView tracks the current tab. Initialized from the viewMode prop
  // (path segment) and kept in sync when the prop changes (back/forward).
  const [activeView, setActiveView] = React.useState<ViewMode | 'doc'>(viewMode)
  React.useEffect(() => { setActiveView(viewMode) }, [viewMode])

  const filesViewActive = activeView === 'files' || activeView === 'doc'
  const graphViewActive = activeView === 'graph'

  // ─── Wiki page selection (from ?p= search param) ─────────────
  const pParam = searchParams.get('p')
  const urlWikiDocNumber = pParam ? parseInt(pParam, 10) : null

  const [wikiActivePath, setWikiActivePath] = React.useState<string | null>(null)
  const [wikiSearchTerm, setWikiSearchTerm] = React.useState('')
  const lastWikiDocNumberRef = React.useRef<number | null>(urlWikiDocNumber)

  // Initialize wikiActivePath from ?p= on mount and when ?p= changes
  React.useEffect(() => {
    if (urlWikiDocNumber == null) return
    if (!documents.length) return
    const doc = documents.find((d) => d.document_number === urlWikiDocNumber)
    if (doc) {
      const path = (doc.path + doc.filename).replace(/^\/wiki\/?/, '')
      setWikiActivePath(path)
      lastWikiDocNumberRef.current = urlWikiDocNumber
    }
  }, [urlWikiDocNumber, documents])

  // ─── Source doc selection ────────────────────────────────────
  // Read ?doc= only on mount (for bookmarked URLs / browser back-forward)
  const initialDocParam = React.useRef(searchParams.get('doc'))
  const initialDocNumber = initialDocParam.current ? parseInt(initialDocParam.current, 10) : null

  const [activeSourceDocId, setActiveSourceDocId] = React.useState<string | null>(() => {
    if (initialDocNumber == null) return null
    const doc = documents.find((d) => d.document_number === initialDocNumber)
    return doc?.id ?? null
  })

  // Resolve initial ?doc= once documents load
  React.useEffect(() => {
    if (initialDocNumber == null || activeSourceDocId) return
    const doc = documents.find((d) => d.document_number === initialDocNumber)
    if (doc) {
      setActiveSourceDocId(doc.id)
      setActiveView('doc')
    }
  }, [initialDocNumber, documents, activeSourceDocId])

  const [filesInitialPage, setFilesInitialPage] = React.useState<number | undefined>()

  // ─── Graph state ─────────────────────────────────────────────
  const [graphFocusNodeId, setGraphFocusNodeId] = React.useState<string | null>(null)

  // ─── Wiki tree ───────────────────────────────────────────────
  const indexDoc = wikiDocs.find((d) => d.filename === 'index.json' && d.path === '/wiki/')
  const SCAFFOLD_FILES = new Set(['index.json', 'overview.md', 'log.md'])
  const hasNavigableWiki = React.useMemo(
    () => wikiDocs.some((d) => d.path === '/wiki/' ? !SCAFFOLD_FILES.has(d.filename) : true),
    [wikiDocs],
  )
  const [wikiTree, setWikiTree] = React.useState<WikiNode[]>([])
  const [indexLoaded, setIndexLoaded] = React.useState(false)

  const wikiDocIds = React.useMemo(() => wikiDocs.map((d) => d.id).join(), [wikiDocs])

  React.useEffect(() => {
    let cancelled = false
    setIndexLoaded(false)
    if (indexDoc) {
      apiFetch<{ content: string }>(`/v1/documents/${indexDoc.id}/content`)
        .then((res) => {
          if (cancelled) return
          try {
            const parsed = JSON.parse(res.content)
            setWikiTree(enrichTreeWithDocNumbers(parsed.tree || [], wikiDocs))
          } catch {
            setWikiTree(buildTreeFromDocs(wikiDocs.filter((d) => d.id !== indexDoc.id)))
          }
          setIndexLoaded(true)
        })
        .catch(() => {
          if (cancelled) return
          setWikiTree(buildTreeFromDocs(wikiDocs.filter((d) => d.id !== indexDoc.id)))
          setIndexLoaded(true)
        })
    } else {
      setWikiTree(buildTreeFromDocs(wikiDocs))
      setIndexLoaded(true)
    }
    return () => { cancelled = true }
  }, [indexDoc?.id, wikiDocIds, wikiDocs])

  // Auto-select first wiki page when none is selected
  React.useEffect(() => {
    if (indexLoaded && activeView === 'wiki' && !wikiActivePath && urlWikiDocNumber == null && wikiTree.length && !loading) {
      const first = findFirstPath(wikiTree)
      if (first) {
        setWikiActivePath(first.path)
        setWikiSearchTerm('')
        lastWikiDocNumberRef.current = first.docNumber
        if (first.docNumber != null) updateParam('p', String(first.docNumber))
      }
    }
  }, [indexLoaded, wikiTree, wikiActivePath, activeView, urlWikiDocNumber, loading, updateParam])

  // ─── Wiki content loading ────────────────────────────────────
  const [pageContent, setPageContent] = React.useState('')
  const [pageTitle, setPageTitle] = React.useState('')
  const [pageLoading, setPageLoading] = React.useState(false)
  const [pageLoadedPath, setPageLoadedPath] = React.useState<string | null>(null)

  const activeWikiDoc = React.useMemo(() => {
    if (!wikiActivePath) return null
    return wikiDocs.find((d) => {
      const relative = (d.path + d.filename).replace(/^\/wiki\/?/, '')
      return relative === wikiActivePath
    }) ?? null
  }, [wikiActivePath, wikiDocs])

  const activeWikiVersion = activeWikiDoc?.version ?? -1
  const activeWikiDocId = activeWikiDoc?.id ?? null

  const wikiBreadcrumbs = React.useMemo((): BreadcrumbItem[] | undefined => {
    if (!wikiActivePath || !wikiTree.length) return undefined
    const crumbs = buildBreadcrumbs(wikiTree, wikiActivePath, kbName)
    return crumbs ?? undefined
  }, [wikiActivePath, wikiTree, kbName])

  React.useEffect(() => {
    if (!wikiActivePath) {
      setPageLoadedPath(null)
      return
    }
    if (!activeWikiDoc) {
      setPageContent(`Page not found: ${wikiActivePath}`)
      setPageTitle('')
      setPageLoadedPath(wikiActivePath)
      return
    }
    setPageTitle(activeWikiDoc.title || activeWikiDoc.filename.replace(/\.(md|txt)$/, ''))
    const isLiveUpdate = pageLoadedPath === wikiActivePath
    if (!isLiveUpdate) {
      setPageLoading(true)
      setPageLoadedPath(null)
    }
    const controller = new AbortController()
    apiFetch<{ content: string }>(`/v1/documents/${activeWikiDoc.id}/content`, { signal: controller.signal })
      .then((res) => {
        if (!controller.signal.aborted) setPageContent(res.content || '')
      })
      .catch((err) => {
        if (!controller.signal.aborted) setPageContent('Failed to load page content.')
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setPageLoading(false)
          setPageLoadedPath(wikiActivePath)
        }
      })
    return () => controller.abort()
  }, [wikiActivePath, activeWikiDocId, activeWikiVersion])

  // ─── Auth guard ───────────────────────────────────────────────
  const requireUser = () => {
    if (!userId) { toast.error('Not authenticated'); return false }
    return true
  }

  // ─── Multi-selection ─────────────────────────────────────────
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set())
  const lastSelectedIdRef = React.useRef<string | null>(null)
  const sourceDocIds = React.useMemo(() => sourceDocs.map((d) => d.id), [sourceDocs])

  const handleSelect = React.useCallback((docId: string, e: React.MouseEvent) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (e.shiftKey && lastSelectedIdRef.current) {
        const lastIdx = sourceDocIds.indexOf(lastSelectedIdRef.current)
        const currIdx = sourceDocIds.indexOf(docId)
        if (lastIdx !== -1 && currIdx !== -1) {
          const [start, end] = lastIdx < currIdx ? [lastIdx, currIdx] : [currIdx, lastIdx]
          for (let i = start; i <= end; i++) next.add(sourceDocIds[i])
        } else {
          next.add(docId)
        }
      } else if (e.metaKey || e.ctrlKey) {
        if (next.has(docId)) next.delete(docId)
        else next.add(docId)
      } else {
        next.clear()
        next.add(docId)
      }
      lastSelectedIdRef.current = docId
      return next
    })
  }, [sourceDocIds])

  const clearSelection = React.useCallback(() => {
    setSelectedIds(new Set())
    lastSelectedIdRef.current = null
  }, [])

  React.useEffect(() => {
    if (selectedIds.size === 0) return
    const handleKeyDown = (e: KeyboardEvent) => { if (e.key === 'Escape') clearSelection() }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [selectedIds.size, clearSelection])

  const handleDeleteSelected = async () => {
    if (!requireUser()) return
    const ids = Array.from(selectedIds)
    if (!window.confirm(`Delete ${ids.length} selected document${ids.length > 1 ? 's' : ''}?`)) return
    const results = await Promise.allSettled(ids.map((id) => apiFetch(`/v1/documents/${id}`, { method: 'DELETE' })))
    const succeeded = ids.filter((_, i) => results[i].status === 'fulfilled')
    const failed = ids.filter((_, i) => results[i].status === 'rejected')
    if (succeeded.length > 0) setDocuments((prev) => prev.filter((d) => !succeeded.includes(d.id)))
    if (failed.length > 0) toast.error(`Failed to delete ${failed.length} document${failed.length > 1 ? 's' : ''}`)
    clearSelection()
  }

  // ─── Navigation handlers ─────────────────────────────────────

  // Wiki page click: only updates ?p= search param (instant, no route change)
  const handleWikiSelect = React.useCallback((path: string, docNumber?: number | null, searchTerm?: string) => {
    setActiveView('wiki')
    setWikiActivePath(path)
    setWikiSearchTerm(searchTerm ?? '')
    const num = docNumber ?? wikiDocs.find((d) => {
      const relative = (d.path + d.filename).replace(/^\/wiki\/?/, '')
      return relative === path
    })?.document_number ?? null
    lastWikiDocNumberRef.current = num
    if (num != null) updateParam('p', String(num))
  }, [updateParam, wikiDocs])

  const handleFilesToggle = React.useCallback(() => {
    if (activeView === 'doc') {
      // Doc is open — close it, go to root file browser
      setActiveSourceDocId(null)
      setActiveView('files')
      navigateToView('files')
    } else if (activeView === 'files') {
      // Already browsing files — toggle back to wiki
      const sp = lastWikiDocNumberRef.current != null
        ? { p: String(lastWikiDocNumberRef.current) }
        : undefined
      setActiveView('wiki')
      navigateToView('wiki', { searchParams: sp })
    } else {
      // From wiki/graph — switch to files
      setActiveView('files')
      navigateToView('files')
    }
  }, [activeView, navigateToView])

  const handleGraphToggle = React.useCallback(() => {
    if (graphViewActive) {
      const sp = lastWikiDocNumberRef.current != null
        ? { p: String(lastWikiDocNumberRef.current) }
        : undefined
      navigateToView('wiki', { searchParams: sp })
    } else {
      setActiveView('graph')
      setGraphFocusNodeId(null)
      navigateToView('graph')
    }
  }, [graphViewActive, navigateToView])

  const handleGraphNodeClick = React.useCallback((docId: string, sourceKind: string) => {
    const doc = documents.find((d) => d.id === docId)
    if (!doc) return
    if (sourceKind === 'wiki') {
      const wikiPath = (doc.path + doc.filename).replace(/^\/wiki\/?/, '')
      setActiveView('wiki')
      setWikiActivePath(wikiPath)
      lastWikiDocNumberRef.current = doc.document_number
      navigateToView('wiki', { searchParams: doc.document_number != null ? { p: String(doc.document_number) } : undefined })
      return
    }
    setActiveSourceDocId(doc.id)
    setActiveView('doc')
    navigateToView('files', { searchParams: doc.document_number != null ? { doc: String(doc.document_number) } : undefined })
  }, [documents, navigateToView])

  const handleOpenSourceDoc = React.useCallback((docId: string) => {
    const doc = documents.find((d) => d.id === docId)
    if (!doc) return
    setActiveSourceDocId(doc.id)
    setActiveView('doc')
    if (doc.document_number != null) {
      navigateToView('files', { searchParams: { doc: String(doc.document_number) } })
    }
  }, [documents, navigateToView])

  const handleCitationSourceClick = React.useCallback((filename: string, page?: number) => {
    const lower = filename.toLowerCase()
    const match = sourceDocs.find((d) => {
      const fn = d.filename.toLowerCase()
      const title = (d.title || '').toLowerCase()
      return fn === lower || title === lower || fn === lower + '.md' || fn.replace(/\.md$/, '') === lower
    })
    if (!match) return
    setActiveSourceDocId(match.id)
    setActiveView('doc')
    setFilesInitialPage(page)
    if (match.document_number != null) {
      navigateToView('files', { searchParams: { doc: String(match.document_number) } })
    }
  }, [sourceDocs, navigateToView])

  const handlePageGraphClick = React.useCallback(() => {
    if (!activeWikiDocId) return
    setActiveView('graph')
    setGraphFocusNodeId(activeWikiDocId)
    navigateToView('graph')
  }, [activeWikiDocId, navigateToView])

  const wikiPathSet = React.useMemo(() => {
    const set = new Set<string>()
    for (const d of wikiDocs) {
      const relative = (d.path + d.filename).replace(/^\/wiki\/?/, '')
      set.add(relative)
    }
    return set
  }, [wikiDocs])

  const handleWikiNavigate = React.useCallback(
    (path: string) => {
      let nextPath = path
      if (path.startsWith('/wiki/')) {
        nextPath = path.replace(/^\/wiki\/?/, '')
      } else if (path.startsWith('/')) {
        nextPath = path.slice(1)
      } else if (wikiPathSet.has(path)) {
        nextPath = path
      } else if (wikiActivePath) {
        const dir = wikiActivePath.includes('/')
          ? wikiActivePath.substring(0, wikiActivePath.lastIndexOf('/'))
          : ''
        let resolved = path.startsWith('./')
          ? (dir ? dir + '/' : '') + path.slice(2)
          : (dir ? dir + '/' : '') + path
        while (resolved.includes('../')) {
          resolved = resolved.replace(/[^/]*\/\.\.\//, '')
        }
        nextPath = resolved
      }
      setWikiActivePath(nextPath)
      const doc = wikiDocs.find((d) => {
        const relative = (d.path + d.filename).replace(/^\/wiki\/?/, '')
        return relative === nextPath
      })
      lastWikiDocNumberRef.current = doc?.document_number ?? null
      if (doc?.document_number != null) updateParam('p', String(doc.document_number))
    },
    [wikiActivePath, wikiPathSet, updateParam, wikiDocs],
  )


  // ─── Document CRUD ───────────────────────────────────────────
  const handleCreateNote = async (targetPath: string = '/') => {
    if (!requireUser() || !userId) return
    try {
      const data = await apiFetch<DocumentListItem>(`/v1/knowledge-bases/${kbId}/documents/note`, {
        method: 'POST',
        body: JSON.stringify({ filename: 'Untitled.md', path: targetPath }),
      })
      setDocuments((prev) => [data, ...prev])
      if (!filesViewActive) {
        setActiveView('files')
        navigateToView('files')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to create note')
    }
  }

  const handleCreateFolder = (folderName: string, parentPath: string = '/') => {
    if (!requireUser() || !userId) return
    const path = parentPath.replace(/\/$/, '') + '/' + folderName + '/'
    apiFetch<DocumentListItem>(`/v1/knowledge-bases/${kbId}/documents/note`, {
      method: 'POST',
      body: JSON.stringify({ filename: 'Untitled.md', path }),
    })
      .then((data) => {
        setDocuments((prev) => [data, ...prev])
        if (!filesViewActive) {
          setActiveView('files')
          navigateToView('files')
        }
      })
      .catch((err: Error) => toast.error(err.message || 'Failed to create folder'))
  }

  const handleMoveDocument = async (docId: string, targetPath: string) => {
    if (!requireUser()) return
    try {
      await apiFetch(`/v1/documents/${docId}`, { method: 'PATCH', body: JSON.stringify({ path: targetPath }) })
      setDocuments((prev) => prev.map((d) => d.id === docId ? { ...d, path: targetPath } : d))
    } catch { toast.error('Failed to move document') }
  }

  const handleDeleteDocument = async (docId: string) => {
    if (!requireUser()) return
    try {
      await apiFetch(`/v1/documents/${docId}`, { method: 'DELETE' })
      setDocuments((prev) => prev.filter((d) => d.id !== docId))
    } catch { toast.error('Failed to delete document') }
  }

  const handleRenameDocument = async (docId: string, newTitle: string) => {
    if (!requireUser()) return
    try {
      await apiFetch(`/v1/documents/${docId}`, { method: 'PATCH', body: JSON.stringify({ title: newTitle }) })
      setDocuments((prev) => prev.map((d) => d.id === docId ? { ...d, title: newTitle } : d))
    } catch { toast.error('Failed to rename document') }
  }

  const handleMoveToSpace = async (docId: string, targetSpaceId: string) => {
    if (!requireUser()) return
    try {
      await apiFetch(`/v1/documents/${docId}/move-to-space`, {
        method: 'POST',
        body: JSON.stringify({ target_space_id: targetSpaceId }),
      })
      setDocuments((prev) => prev.filter((d) => d.id !== docId))
      const targetKB = useKBStore.getState().knowledgeBases.find((kb) => kb.id === targetSpaceId)
      if (targetKB) {
        window.location.href = `/wikis/${targetKB.slug}`
      }
      toast.success('Page moved successfully')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to move page')
    }
  }

  const handleCopyToSpace = async (docId: string, targetSpaceId: string) => {
    if (!requireUser()) return
    try {
      await apiFetch(`/v1/documents/${docId}/copy-to-space`, {
        method: 'POST',
        body: JSON.stringify({ target_space_id: targetSpaceId }),
      })
      toast.success('Page copied to space')
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to copy page')
    }
  }

  // ─── File upload ─────────────────────────────────────────────
  const uploadPathRef = React.useRef('/')
  const handleUploadClick = (targetPath: string = '/') => {
    uploadPathRef.current = targetPath
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.md,.txt,.pdf,.pptx,.ppt,.docx,.doc,.png,.jpg,.jpeg,.webp,.gif,.svg,.xlsx,.xls,.csv,.html,.htm'
    input.multiple = true
    input.onchange = () => { if (input.files) uploadFiles(Array.from(input.files), uploadPathRef.current) }
    input.click()
  }

  const tusUploadFile = React.useCallback((file: File, targetPath: string = '/'): Promise<void> => {
    return new Promise((resolve, reject) => {
      const upload = new tus.Upload(file, {
        endpoint: `${API_URL}/v1/uploads`,
        retryDelays: [0, 1000, 3000, 5000],
        metadata: { filename: file.name, knowledge_base_id: kbId, path: targetPath },
        // Cookies are sent automatically — no Authorization header needed
        onError: (error) => { toast.error(`Upload failed: ${file.name}`); reject(error) },
        onSuccess: () => { toast.success(`${file.name} uploaded, processing...`); resolve() },
      })
      upload.start()
    })
  }, [kbId])

  const uploadFiles = React.useCallback((files: File[], targetPath: string = '/') => {
    if (!requireUser() || !userId) return

    // Client-side duplicate check — documents are already loaded
    const existingNames = new Set(
      documents
        .filter((d) => d.path === targetPath && !d.archived)
        .map((d) => d.filename.toLowerCase()),
    )
    const duplicates = files.filter((f) => existingNames.has(f.name.toLowerCase()))
    if (duplicates.length > 0) {
      const names = duplicates.map((f) => f.name).join(', ')
      toast.error(`Already exists: ${names}`)
      if (duplicates.length === files.length) return
      files = files.filter((f) => !existingNames.has(f.name.toLowerCase()))
    }

    const uploads = files.map(async (file) => {
      const ext = file.name.split('.').pop()?.toLowerCase()
      if (ext === 'md' || ext === 'txt') {
        const content = await file.text()
        const title = file.name.replace(/\.(md|txt)$/i, '')
        try {
          const data = await apiFetch<DocumentListItem>(`/v1/knowledge-bases/${kbId}/documents/note`, {
            method: 'POST',
            body: JSON.stringify({ filename: file.name, title, content, path: targetPath }),
          })
          setDocuments((prev) => [data, ...prev])
        } catch { toast.error(`Failed to import ${file.name}`) }
      } else {
        const supportedTypes = new Set(['pdf', 'pptx', 'ppt', 'docx', 'doc', 'png', 'jpg', 'jpeg', 'webp', 'gif', 'xlsx', 'xls', 'csv', 'html', 'htm'])
        if (ext && supportedTypes.has(ext)) {
          if (process.env.NEXT_PUBLIC_MODE === 'local') {
            const formData = new FormData()
            formData.append('file', file)
            formData.append('path', targetPath)
            try {
              const res = await fetch(`${API_URL}/v1/upload`, { method: 'POST', body: formData })
              if (!res.ok) throw new Error(`Upload failed: ${res.status}`)
              const data = await res.json()
              setDocuments((prev) => [data, ...prev])
              toast.success(`${file.name} uploaded`)
            } catch { toast.error(`Upload failed: ${file.name}`) }
          } else {
            await tusUploadFile(file, targetPath)
          }
        } else {
          toast.info(`${ext} files not yet supported`)
        }
      }
    })
    Promise.all(uploads).then(() => {
      const textFiles = files.filter((f) => /\.(md|txt)$/i.test(f.name))
      if (textFiles.length > 0) toast.success(`Imported ${textFiles.length} file${textFiles.length > 1 ? 's' : ''}`)
      // Navigate to files view after first upload
      if (sourceDocs.length === 0) {
        setActiveView('files')
        navigateToView('files')
      }
    })
  }, [kbId, userId, tusUploadFile, documents, sourceDocs.length, navigateToView])

  // ─── Drag-and-drop ───────────────────────────────────────────
  const [fileDragOver, setFileDragOver] = React.useState(false)
  const dragCounterRef = React.useRef(0)

  const handleFileDragEnter = (e: React.DragEvent) => {
    if (filesViewActive) return
    if (e.dataTransfer.types.includes('application/x-llmwiki-item')) return
    e.preventDefault()
    dragCounterRef.current++
    if (dragCounterRef.current === 1) setFileDragOver(true)
  }
  const handleFileDragLeave = (e: React.DragEvent) => {
    if (filesViewActive) return
    e.preventDefault()
    dragCounterRef.current--
    if (dragCounterRef.current === 0) setFileDragOver(false)
  }
  const handleFileDragOver = (e: React.DragEvent) => {
    if (filesViewActive) return
    if (e.dataTransfer.types.includes('application/x-llmwiki-item')) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }
  const handleFileDrop = (e: React.DragEvent) => {
    if (filesViewActive) return
    if (e.dataTransfer.types.includes('application/x-llmwiki-item')) return
    e.preventDefault()
    dragCounterRef.current = 0
    setFileDragOver(false)
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) uploadFiles(files)
  }

  // ─── FilesGrid URL-sync callbacks ────────────────────────────
  const handleFilesPathChange = React.useCallback((path: string) => {
    const clean = path === '/' ? '' : path.replace(/^\//, '').replace(/\/$/, '')
    const url = `/wikis/${kbSlug}` + (clean ? `/files/${encodeURI(clean)}` : '/files')
    // Use replaceState to update the URL bar without triggering a Next.js
    // navigation — avoids re-rendering the page component and the flash
    // that comes from KBPage → KBDetail → FilesGrid prop cascade.
    window.history.replaceState(window.history.state, '', url)
  }, [kbSlug])

  const handleFilesDocOpen = React.useCallback((docNumber: number | null) => {
    if (docNumber == null) return
    const doc = documents.find((d) => d.document_number === docNumber)
    if (doc) {
      setActiveSourceDocId(doc.id)
      setActiveView('doc')
      updateParam('doc', String(docNumber))
    }
  }, [documents, updateParam])

  const handleFilesDocClose = React.useCallback(() => {
    setActiveSourceDocId(null)
    setActiveView('files')
    updateParam('doc', null)
  }, [updateParam])

  // ─── Loading state ───────────────────────────────────────────
  const showMainLoading =
    loading ||
    (!filesViewActive && !graphViewActive && hasNavigableWiki && !wikiActivePath) ||
    (!filesViewActive && !graphViewActive && !!wikiActivePath && pageLoadedPath !== wikiActivePath)

  // ─── Render ──────────────────────────────────────────────────
  return (
    <div
      className="flex flex-col h-full relative"
      onDragEnter={handleFileDragEnter}
      onDragLeave={handleFileDragLeave}
      onDragOver={handleFileDragOver}
      onDrop={handleFileDrop}
    >
      <AnimatePresence>
        {fileDragOver && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center pointer-events-none"
          >
            <div className="flex flex-col items-center gap-3 border-2 border-dashed border-primary rounded-xl px-12 py-10">
              <UploadIcon className="size-8 text-primary" />
              <p className="text-sm font-medium text-primary">Drop files to upload</p>
              <p className="text-xs text-muted-foreground">PDF, Word, PowerPoint, images, and more</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex-1 overflow-hidden flex relative">
        {/* Backdrop (mobile only) */}
        {sidenavOpen && (
          <div
            className="fixed inset-0 z-30 bg-background/60 backdrop-blur-sm md:hidden"
            onClick={() => setSidenavOpen(false)}
          />
        )}

        {/* Sidebar — overlay en móvil, en-flujo en desktop */}
        <div
          className={cn(
            "shrink-0 h-full bg-background",
            "fixed top-0 bottom-0 left-0 z-40",
            "md:relative md:top-auto md:bottom-auto md:left-auto md:z-auto",
            "transition-transform duration-200 ease-out",
            sidenavOpen ? "translate-x-0" : "-translate-x-full",
            "md:translate-x-0",
          )}
          style={{ width: sidenavWidth }}
        >
          <KBSidenav
            kbId={kbId}
            kbName={kbName}
            wikiTree={wikiTree}
            wikiActivePath={filesViewActive || graphViewActive ? null : wikiActivePath}
            onWikiNavigate={handleWikiSelect}
            sourceDocs={sourceDocs}
            hasWiki={hasNavigableWiki}
            loading={loading}
            onUpload={() => handleUploadClick()}
            filesViewActive={filesViewActive}
            onFilesToggle={handleFilesToggle}
            graphViewActive={graphViewActive}
            onGraphToggle={handleGraphToggle}
            onOpenSourceDoc={handleOpenSourceDoc}
            onClose={() => setSidenavOpen(false)}
            onMoveToSpace={handleMoveToSpace}
            onCopyToSpace={handleCopyToSpace}
            workspaceSlug={workspaceSlug}
            workspaceName={workspaceName}
            ownerName={ownerName}
          />
        </div>

        {/* Resize handle — desktop only */}
        <div
          onMouseDown={handleResizeMouseDown}
          className="hidden md:flex shrink-0 w-1 cursor-col-resize items-stretch group z-10"
        >
          <div className="w-px bg-border group-hover:bg-primary/40 transition-colors duration-150 mx-auto" />
        </div>

        {/* Contenido principal */}
        <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
          {/* Header mobile con hamburguesa */}
          <div className="md:hidden flex items-center gap-3 px-4 h-12 border-b border-border shrink-0">
            <button
              onClick={() => setSidenavOpen(true)}
              className="p-1.5 rounded-md hover:bg-accent text-muted-foreground cursor-pointer"
              aria-label="Abrir menú"
            >
              <Menu className="size-4" />
            </button>
            <span className="text-sm font-medium truncate">{pageTitle || kbName}</span>
          </div>

          <div className="flex-1 overflow-hidden">
          <AnimatePresence mode="wait">
            {showMainLoading ? (
              <motion.div
                key="loading"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.1 }}
                className="flex items-center justify-center h-full"
              >
                <Loader2 className="size-5 animate-spin text-muted-foreground" />
              </motion.div>
            ) : graphViewActive ? (
              <motion.div
                key="graph"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.15, ease: [0.25, 0.1, 0.25, 1] }}
                className="h-full"
              >
                <GraphViewer
                  kbId={kbId}
                  focusNodeId={graphFocusNodeId}
                  onNavigateToDoc={handleGraphNodeClick}
                />
              </motion.div>
            ) : filesViewActive ? (
              <motion.div
                key="files"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.15, ease: [0.25, 0.1, 0.25, 1] }}
                className="h-full"
              >
                <FilesGrid
                  key={kbId}
                  documents={documents}
                  onDeleteDocument={handleDeleteDocument}
                  onRenameDocument={handleRenameDocument}
                  onUpload={handleUploadClick}
                  onCreateNote={handleCreateNote}
                  onCreateFolder={handleCreateFolder}
                  onMoveDocument={handleMoveDocument}
                  onUploadFiles={uploadFiles}
                  initialDocId={activeSourceDocId}
                  initialPage={filesInitialPage}
                  initialPath={routeFilesPath}
                  onPathChange={handleFilesPathChange}
                  onDocOpen={handleFilesDocOpen}
                  onDocClose={handleFilesDocClose}
                />
              </motion.div>
            ) : pageLoading ? (
              <motion.div
                key="wiki-loading"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.1 }}
                className="flex items-center justify-center h-full"
              >
                <Loader2 className="size-5 animate-spin text-muted-foreground" />
              </motion.div>
            ) : hasNavigableWiki && wikiActivePath ? (
              <motion.div
                key={`wiki-${wikiActivePath}`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15, ease: [0.25, 0.1, 0.25, 1] }}
                className="h-full"
              >
                <WikiContent
                  content={pageContent}
                  title={pageTitle}
                  onNavigate={handleWikiNavigate}
                  onSourceClick={handleCitationSourceClick}
                  onGraphClick={handlePageGraphClick}
                  documents={documents}
                  breadcrumbs={wikiBreadcrumbs}
                  searchTerm={wikiSearchTerm}
                  docId={activeWikiDocId}
                />
              </motion.div>
            ) : (
              <motion.div
                key="empty"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2, ease: [0.25, 0.1, 0.25, 1] }}
                className="flex flex-col items-center justify-center h-full gap-4 px-6"
              >
                <BookOpen className="size-10 text-muted-foreground/20" />
                <div className="text-center max-w-sm">
                  <h3 className="text-base font-medium mb-1.5">No wiki yet</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    Add some sources, then ask Claude to compile a wiki from them.
                  </p>
                </div>
                <div className="flex items-center gap-3 mt-2">
                  <button
                    onClick={() => handleUploadClick()}
                    className="inline-flex items-center gap-2 rounded-full bg-foreground text-background px-5 py-2 text-sm font-medium hover:opacity-90 transition-opacity cursor-pointer"
                  >
                    <UploadIcon className="size-3.5 opacity-60" />
                    Upload Sources
                  </button>
                  <a
                    href="https://claude.ai"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 rounded-full border border-border px-5 py-2 text-sm font-medium hover:bg-accent transition-colors"
                  >
                    Open Claude
                    <ArrowUpRight className="size-3.5 opacity-60" />
                  </a>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          </div>
        </div>
      </div>

      <SelectionActionBar
        count={selectedIds.size}
        onDelete={handleDeleteSelected}
        onClear={clearSelection}
      />
    </div>
  )
}
