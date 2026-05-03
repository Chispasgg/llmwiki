import { create } from 'zustand'

type User = {
  id: string
  email: string
  display_name: string
  role: 'superadmin' | 'admin' | 'editor' | 'viewer'
}

type UserState = {
  user: User | null
  authLoading: boolean
  setUser: (user: User | null) => void
  setAuthLoading: (loading: boolean) => void
  signOut: () => void
}

export const useUserStore = create<UserState>()((set) => ({
  user: null,
  authLoading: true,
  setUser: (user) => set({ user, authLoading: false }),
  setAuthLoading: (authLoading) => set({ authLoading }),
  signOut: () => set({ user: null, authLoading: false }),
}))
