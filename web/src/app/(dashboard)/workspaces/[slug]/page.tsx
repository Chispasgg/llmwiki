'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  ArrowLeft, Plus, BookOpen, FileText, Clock,
  MoreHorizontal, MoveRight, Loader2, Search,
} from 'lucide-react'
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
} from '@/components/ui/dropdown-menu'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { toast } from 'sonner'
import { apiFetch } from '@/lib/api'
import { useWorkspaceStore, useKBStore, useUserStore } from '@/stores'
import type { KnowledgeBase, Workspace } from '@/lib/types'

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  return `${Math.floor(days / 30)}mo ago`
}

function WikiCard({
  kb,
  onOpen,
  onMove,
}: {
  kb: KnowledgeBase
  onOpen: () => void
  onMove: () => void
}) {
  return (
    <div className="group rounded-xl border border-border bg-card hover:bg-accent/20 transition-colors p-5 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <button
          onClick={onOpen}
          className="flex-1 text-left text-base font-semibold text-foreground hover:text-primary transition-colors leading-tight cursor-pointer"
        >
          {kb.name}
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="p-1 rounded hover:bg-accent transition-colors opacity-0 group-hover:opacity-100 cursor-pointer">
              <MoreHorizontal className="size-4 text-muted-foreground" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onMove}>
              <MoveRight className="size-3.5 mr-2" />
              Move to workspace…
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {kb.description && (
        <p className="text-sm text-muted-foreground line-clamp-2">{kb.description}</p>
      )}
      <div className="flex items-center gap-4 mt-auto pt-1">
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <FileText className="size-3.5" />
          {kb.wiki_page_count} pages
        </span>
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <BookOpen className="size-3.5" />
          {kb.source_count} sources
        </span>
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground ml-auto">
          <Clock className="size-3.5" />
          {relativeTime(kb.updated_at)}
        </span>
      </div>
    </div>
  )
}

function MoveWikiModal({
  open,
  onClose,
  kb,
  currentWorkspaceId,
  onMoved,
}: {
  open: boolean
  onClose: () => void
  kb: KnowledgeBase | null
  currentWorkspaceId: string
  onMoved: (kbId: string) => void
}) {
  const workspaces = useWorkspaceStore((s) => s.workspaces)
  const [selected, setSelected] = React.useState<string | null>(null)
  const [moving, setMoving] = React.useState(false)
  const choices = workspaces.filter((w) => w.id !== currentWorkspaceId)

  React.useEffect(() => { if (!open) setSelected(null) }, [open])

  const handleMove = async () => {
    if (!selected || !kb) return
    setMoving(true)
    try {
      await apiFetch(`/v1/workspaces/wikis/${kb.id}/move`, {
        method: 'POST',
        body: JSON.stringify({ target_workspace_id: selected }),
      })
      toast.success(`"${kb.name}" moved successfully`)
      onMoved(kb.id)
      onClose()
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to move wiki')
    } finally {
      setMoving(false)
    }
  }

  if (!open) return null

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Move &ldquo;{kb?.name}&rdquo; to workspace</DialogTitle>
        </DialogHeader>
        <div className="space-y-1 max-h-60 overflow-y-auto">
          {choices.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">No other workspaces available</p>
          ) : choices.map((ws) => (
            <button
              key={ws.id}
              onClick={() => setSelected(ws.id)}
              className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors cursor-pointer ${
                selected === ws.id ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'
              }`}
            >
              {ws.name}
            </button>
          ))}
        </div>
        <DialogFooter>
          <button onClick={onClose} className="px-3 py-1.5 text-sm border rounded-md hover:bg-accent cursor-pointer">
            Cancel
          </button>
          <button
            disabled={!selected || moving}
            onClick={handleMove}
            className="px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded-md hover:opacity-90 disabled:opacity-50 cursor-pointer"
          >
            {moving ? 'Moving…' : 'Move'}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function WorkspaceDetailPage() {
  const params = useParams<{ slug: string }>()
  const router = useRouter()
  const { workspaces, fetchWorkspaces, updateWorkspace } = useWorkspaceStore()
  const createKB = useKBStore((s) => s.createKB)
  const user = useUserStore((s) => s.user)
  const [ws, setWs] = React.useState<Workspace | null>(null)
  const [wikis, setWikis] = React.useState<KnowledgeBase[]>([])
  const [loading, setLoading] = React.useState(true)
  const [search, setSearch] = React.useState('')
  const [moveTarget, setMoveTarget] = React.useState<KnowledgeBase | null>(null)
  const [createOpen, setCreateOpen] = React.useState(false)
  const [newKBName, setNewKBName] = React.useState('')
  const [creating, setCreating] = React.useState(false)
  const [editOpen, setEditOpen] = React.useState(false)
  const [editName, setEditName] = React.useState('')
  const [editDescription, setEditDescription] = React.useState('')
  const [saving, setSaving] = React.useState(false)

  const canEdit = ws !== null && user !== null && (
    user.role === 'superadmin' || user.id === ws.created_by
  )

  const openEdit = () => {
    if (!ws) return
    setEditName(ws.name)
    setEditDescription(ws.description ?? '')
    setEditOpen(true)
  }

  const handleSave = async () => {
    if (!ws || !editName.trim()) return
    setSaving(true)
    try {
      const updated = await updateWorkspace(
        ws.id,
        editName.trim(),
        editDescription.trim() || null,
      )
      setWs(updated)
      setEditOpen(false)
      toast.success('Workspace updated')
      if (updated.slug !== ws.slug) {
        router.replace(`/workspaces/${updated.slug}`)
      }
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to update workspace')
    } finally {
      setSaving(false)
    }
  }

  React.useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        let wsList = workspaces
        if (!wsList.length) wsList = await fetchWorkspaces()
        const found = wsList.find((w) => w.slug === params.slug) ?? null
        setWs(found)
        if (found) {
          const kbs = await apiFetch<KnowledgeBase[]>(`/v1/workspaces/${found.id}/wikis`)
          setWikis(kbs)
        }
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [params.slug])

  const filteredWikis = React.useMemo(() => {
    const sorted = [...wikis].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    )
    if (!search.trim()) return sorted
    const q = search.toLowerCase()
    return sorted.filter((kb) => kb.name.toLowerCase().includes(q))
  }, [wikis, search])

  const handleCreateKB = async () => {
    if (!newKBName.trim() || !ws) return
    setCreating(true)
    try {
      const kb = await createKB(newKBName.trim())
      await apiFetch(`/v1/workspaces/wikis/${kb.id}/move`, {
        method: 'POST',
        body: JSON.stringify({ target_workspace_id: ws.id }),
      })
      router.push(`/wikis/${kb.slug}`)
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to create wiki')
    } finally {
      setCreating(false)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!ws) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-10 text-center text-muted-foreground">
        Workspace not found.
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-5xl mx-auto px-6 py-10">
        <div className="mb-8">
          <button
            onClick={() => router.push('/workspaces')}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4 transition-colors cursor-pointer"
          >
            <ArrowLeft className="size-3.5" />
            All workspaces
          </button>
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-2">
              <div>
                <h1 className="text-2xl font-bold text-foreground">{ws.name}</h1>
                {ws.description && (
                  <p className="text-sm text-muted-foreground mt-1">{ws.description}</p>
                )}
              </div>
              {canEdit && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button className="p-1.5 rounded-md hover:bg-accent transition-colors text-muted-foreground hover:text-foreground cursor-pointer shrink-0 self-start mt-0.5">
                      <MoreHorizontal className="size-4" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start">
                    <DropdownMenuItem onClick={openEdit}>
                      Rename workspace
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={openEdit}>
                      Change description
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
            <button
              onClick={() => setCreateOpen(true)}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-lg hover:opacity-90 transition-opacity cursor-pointer shrink-0"
            >
              <Plus className="size-4" />
              New wiki
            </button>
          </div>

          {wikis.length > 0 && (
            <div className="mt-5 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search wikis…"
                className="w-full sm:w-72 rounded-lg border border-input bg-background pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          )}
        </div>

        {wikis.length === 0 ? (
          <div className="text-center py-20 text-muted-foreground">
            <p>No wikis in this workspace yet.</p>
          </div>
        ) : filteredWikis.length === 0 ? (
          <div className="text-center py-20 text-muted-foreground">
            <p>No wikis match &ldquo;{search}&rdquo;.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredWikis.map((kb) => (
              <WikiCard
                key={kb.id}
                kb={kb}
                onOpen={() => router.push(`/wikis/${kb.slug}`)}
                onMove={() => setMoveTarget(kb)}
              />
            ))}
          </div>
        )}
      </div>

      <MoveWikiModal
        open={!!moveTarget}
        onClose={() => setMoveTarget(null)}
        kb={moveTarget}
        currentWorkspaceId={ws.id}
        onMoved={(kbId) => setWikis((prev) => prev.filter((k) => k.id !== kbId))}
      />

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New wiki in {ws.name}</DialogTitle>
          </DialogHeader>
          <input
            value={newKBName}
            onChange={(e) => setNewKBName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreateKB()}
            placeholder="Wiki name"
            autoFocus
            className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
          />
          <DialogFooter>
            <button
              onClick={handleCreateKB}
              disabled={creating || !newKBName.trim()}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50 cursor-pointer"
            >
              {creating ? 'Creating…' : 'Create'}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={editOpen} onOpenChange={(v) => { if (!saving) setEditOpen(v) }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Edit workspace</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium text-foreground">Name</label>
              <input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSave()}
                placeholder="Workspace name"
                autoFocus
                className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-foreground">Description</label>
              <textarea
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                placeholder="Optional description"
                rows={3}
                className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
              />
            </div>
          </div>
          <DialogFooter>
            <button
              onClick={() => setEditOpen(false)}
              disabled={saving}
              className="px-3 py-1.5 text-sm border rounded-md hover:bg-accent cursor-pointer disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !editName.trim()}
              className="px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded-md hover:opacity-90 disabled:opacity-50 cursor-pointer"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
