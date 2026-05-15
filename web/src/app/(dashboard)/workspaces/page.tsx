'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { Plus, Users, BookOpen, Loader2 } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { useWorkspaceStore } from '@/stores'
import type { Workspace } from '@/lib/types'

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

function WorkspaceCard({ ws, onClick }: { ws: Workspace; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="group text-left w-full rounded-xl border border-border bg-card hover:bg-accent/40 transition-colors p-5 flex flex-col gap-3 cursor-pointer"
    >
      <div className="flex items-start justify-between gap-2">
        <h2 className="text-base font-semibold text-foreground group-hover:text-primary transition-colors leading-tight">
          {ws.name}
        </h2>
        <span className="text-[10px] text-muted-foreground/50 shrink-0 mt-0.5">
          {relativeTime(ws.updated_at)}
        </span>
      </div>
      {ws.description && (
        <p className="text-sm text-muted-foreground line-clamp-2">{ws.description}</p>
      )}
      <div className="flex items-center gap-4 mt-auto pt-1">
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <BookOpen className="size-3.5" />
          {ws.wiki_count} {ws.wiki_count === 1 ? 'wiki' : 'wikis'}
        </span>
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Users className="size-3.5" />
          {ws.member_count} {ws.member_count === 1 ? 'member' : 'members'}
        </span>
      </div>
    </button>
  )
}

export default function WorkspacesPage() {
  const router = useRouter()
  const { workspaces, loading, fetchWorkspaces, createWorkspace } = useWorkspaceStore()
  const [createOpen, setCreateOpen] = React.useState(false)
  const [newName, setNewName] = React.useState('')
  const [newDesc, setNewDesc] = React.useState('')
  const [creating, setCreating] = React.useState(false)

  React.useEffect(() => { fetchWorkspaces() }, [])

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    try {
      const ws = await createWorkspace(newName.trim(), newDesc.trim() || undefined)
      setCreateOpen(false)
      setNewName('')
      setNewDesc('')
      router.push(`/workspaces/${ws.slug}`)
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-5xl mx-auto px-6 py-10">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Workspaces</h1>
            <p className="text-sm text-muted-foreground mt-1">Select a workspace to view its wikis</p>
          </div>
          <button
            onClick={() => setCreateOpen(true)}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-lg hover:opacity-90 transition-opacity cursor-pointer"
          >
            <Plus className="size-4" />
            New workspace
          </button>
        </div>

        {loading ? (
          <div className="flex justify-center py-20">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          </div>
        ) : workspaces.length === 0 ? (
          <div className="text-center py-20 text-muted-foreground">
            <p>No workspaces yet. Create your first one.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {workspaces.map((ws) => (
              <WorkspaceCard
                key={ws.id}
                ws={ws}
                onClick={() => router.push(`/workspaces/${ws.slug}`)}
              />
            ))}
          </div>
        )}
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create workspace</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              placeholder="Workspace name"
              autoFocus
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
            />
            <textarea
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="Description (optional)"
              rows={3}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm resize-none"
            />
          </div>
          <DialogFooter>
            <button
              onClick={handleCreate}
              disabled={creating || !newName.trim()}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50 cursor-pointer"
            >
              {creating ? 'Creating...' : 'Create'}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
