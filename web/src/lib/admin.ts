import { apiFetch } from './api'

// ── Types ──────────────────────────────────────────────────────

export interface AdminUser {
  id: string
  email: string
  display_name: string
  role: 'superadmin' | 'admin' | 'editor' | 'viewer'
  is_active: boolean
  created_at: string
  last_login_at: string | null
}

export interface AdminAPIKey {
  id: string
  user_id: string
  user_email: string
  name: string | null
  key_prefix: string
  is_active: boolean
  created_at: string
  last_used_at: string | null
  revoked_at: string | null
}

export interface AdminKB {
  id: string
  user_id: string
  user_email: string
  name: string
  slug: string
  description: string | null
  is_shared: boolean
  created_at: string
}

export interface UsageLog {
  id: number
  user_id: string | null
  user_email: string | null
  action: string
  resource_type: string | null
  resource_id: string | null
  kb_id: string | null
  metadata: Record<string, unknown> | null
  ip_address: string | null
  created_at: string
}

export interface GlobalStats {
  total_users: number
  total_documents: number
  total_pages: number
  total_storage_bytes: number
  global_max_users: number
  quota_max_pages_per_user: number
  quota_max_storage_per_user: number
}

// ── Users ──────────────────────────────────────────────────────

export const listUsers = () =>
  apiFetch<AdminUser[]>('/v1/admin/users')

export const createUser = (body: {
  email: string
  password: string
  display_name: string
  role: string
}) =>
  apiFetch<AdminUser>('/v1/admin/users', {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const updateUser = (
  userId: string,
  body: { role?: string; is_active?: boolean; display_name?: string; password?: string },
) =>
  apiFetch<AdminUser>(`/v1/admin/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })

export const deleteUser = (userId: string) =>
  apiFetch<void>(`/v1/admin/users/${userId}`, { method: 'DELETE' })

// ── API Keys ────────────────────────────────────────────────────

export const listAllAPIKeys = () =>
  apiFetch<AdminAPIKey[]>('/v1/superadmin/api-keys')

export const revokeAnyAPIKey = (keyId: string) =>
  apiFetch<void>(`/v1/superadmin/api-keys/${keyId}`, { method: 'DELETE' })

// ── Knowledge Bases ─────────────────────────────────────────────

export const listAllKBs = () =>
  apiFetch<AdminKB[]>('/v1/superadmin/knowledge-bases')

export const deleteAnyKB = (kbId: string) =>
  apiFetch<void>(`/v1/superadmin/knowledge-bases/${kbId}`, { method: 'DELETE' })

// ── Shares ──────────────────────────────────────────────────────

export interface AdminShare {
  id: string
  kb_id: string
  kb_name: string
  kb_slug: string
  owner_email: string
  shared_with_id: string
  shared_with_email: string
  shared_with_display_name: string
  access_level: 'viewer' | 'editor'
  created_at: string
}

export const listAllShares = () =>
  apiFetch<AdminShare[]>('/v1/superadmin/shares')

export const deleteAnyShare = (shareId: string) =>
  apiFetch<void>(`/v1/superadmin/shares/${shareId}`, { method: 'DELETE' })

// ── Stats ───────────────────────────────────────────────────────

export const getGlobalStats = () =>
  apiFetch<GlobalStats>('/v1/admin/stats')

// ── Logs ────────────────────────────────────────────────────────

export const listUsageLogs = (params?: { limit?: number; offset?: number; action?: string }) => {
  const qs = new URLSearchParams()
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('offset', String(params.offset))
  if (params?.action) qs.set('action', params.action)
  return apiFetch<UsageLog[]>(`/v1/superadmin/logs?${qs}`)
}
