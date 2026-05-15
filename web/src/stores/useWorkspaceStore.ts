import { create } from 'zustand'
import { apiFetch } from '@/lib/api'
import type { Workspace } from '@/lib/types'

interface WorkspaceState {
  workspaces: Workspace[]
  loading: boolean
  fetchWorkspaces: () => Promise<Workspace[]>
  createWorkspace: (name: string, description?: string) => Promise<Workspace>
  deleteWorkspace: (id: string) => Promise<void>
  moveWiki: (kbId: string, targetWorkspaceId: string) => Promise<void>
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  workspaces: [],
  loading: false,

  fetchWorkspaces: async () => {
    set({ loading: true })
    try {
      const data = await apiFetch<Workspace[]>('/v1/workspaces')
      set({ workspaces: data, loading: false })
      return data
    } catch {
      set({ loading: false })
      return []
    }
  },

  createWorkspace: async (name, description) => {
    const ws = await apiFetch<Workspace>('/v1/workspaces', {
      method: 'POST',
      body: JSON.stringify({ name, description }),
    })
    set((s) => ({ workspaces: [...s.workspaces, ws] }))
    return ws
  },

  deleteWorkspace: async (id) => {
    await apiFetch(`/v1/workspaces/${id}`, { method: 'DELETE' })
    set((s) => ({ workspaces: s.workspaces.filter((w) => w.id !== id) }))
  },

  moveWiki: async (kbId, targetWorkspaceId) => {
    await apiFetch(`/v1/workspaces/wikis/${kbId}/move`, {
      method: 'POST',
      body: JSON.stringify({ target_workspace_id: targetWorkspaceId }),
    })
  },
}))
