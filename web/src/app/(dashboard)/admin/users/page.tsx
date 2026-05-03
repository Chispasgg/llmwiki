'use client'

import { useEffect, useState } from 'react'
import { Key, X, Check } from 'lucide-react'
import {
  listUsers, createUser, updateUser, deleteUser,
  type AdminUser,
} from '@/lib/admin'
import { useUserStore } from '@/stores'

const ROLES = ['superadmin', 'admin', 'editor', 'viewer'] as const
const PROTECTED = 'patxigg@biklabs.ai'

export default function AdminUsersPage() {
  const currentUser = useUserStore((s) => s.user)
  const canChangePasswords = currentUser?.email?.toLowerCase() === PROTECTED
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [newUser, setNewUser] = useState({
    email: '', password: '', display_name: '', role: 'viewer',
  })
  const [creating, setCreating] = useState(false)
  const [pwdEditId, setPwdEditId] = useState<string | null>(null)
  const [pwdValue, setPwdValue] = useState('')
  const [pwdSaving, setPwdSaving] = useState(false)

  const load = () => {
    setLoading(true)
    listUsers()
      .then(setUsers)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    try {
      await createUser(newUser)
      setNewUser({ email: '', password: '', display_name: '', role: 'viewer' })
      load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setCreating(false)
    }
  }

  const handleRoleChange = async (user: AdminUser, role: string) => {
    try {
      await updateUser(user.id, { role })
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleToggleActive = async (user: AdminUser) => {
    try {
      await updateUser(user.id, { is_active: !user.is_active })
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleDelete = async (user: AdminUser) => {
    if (!confirm(`¿Eliminar usuario ${user.email}?`)) return
    try {
      await deleteUser(user.id)
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const startPwdEdit = (userId: string) => {
    setPwdEditId(userId)
    setPwdValue('')
  }

  const cancelPwdEdit = () => {
    setPwdEditId(null)
    setPwdValue('')
  }

  const handlePwdSave = async (userId: string) => {
    if (!pwdValue.trim()) return
    setPwdSaving(true)
    try {
      await updateUser(userId, { password: pwdValue })
      cancelPwdEdit()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setPwdSaving(false)
    }
  }

  if (loading) return <p className="text-muted-foreground">Cargando...</p>

  return (
    <div>
      <h1 className="text-xl font-semibold mb-6">Gestión de usuarios</h1>
      {error && <p className="text-destructive mb-4">{error}</p>}

      <form onSubmit={handleCreate} className="mb-8 grid grid-cols-2 gap-3 max-w-lg">
        <input
          placeholder="Email"
          value={newUser.email}
          onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
          className="col-span-2 border rounded px-3 py-2 text-sm"
          required type="email"
        />
        <input
          placeholder="Nombre"
          value={newUser.display_name}
          onChange={(e) => setNewUser({ ...newUser, display_name: e.target.value })}
          className="border rounded px-3 py-2 text-sm"
          required
        />
        <input
          placeholder="Contraseña"
          value={newUser.password}
          onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
          className="border rounded px-3 py-2 text-sm"
          required type="password"
        />
        <select
          value={newUser.role}
          onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
          className="border rounded px-3 py-2 text-sm"
        >
          {ROLES.map((r) => <option key={r}>{r}</option>)}
        </select>
        <button
          type="submit"
          disabled={creating}
          className="bg-primary text-primary-foreground rounded px-4 py-2 text-sm"
        >
          {creating ? 'Creando...' : 'Crear usuario'}
        </button>
      </form>

      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-2 pr-4">Email</th>
            <th className="py-2 pr-4">Nombre</th>
            <th className="py-2 pr-4">Rol</th>
            <th className="py-2 pr-4">Activo</th>
            <th className="py-2 pr-4">Último acceso</th>
            <th className="py-2">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => {
            const isProtected = u.email.toLowerCase() === PROTECTED
            const editingPwd = pwdEditId === u.id
            return (
              <tr key={u.id} className="border-b hover:bg-muted/40">
                <td className="py-2 pr-4">{u.email}</td>
                <td className="py-2 pr-4">{u.display_name}</td>
                <td className="py-2 pr-4">
                  {isProtected ? (
                    <span className="text-muted-foreground">{u.role}</span>
                  ) : (
                    <select
                      value={u.role}
                      onChange={(e) => handleRoleChange(u, e.target.value)}
                      className="border rounded px-2 py-1 text-xs"
                    >
                      {ROLES.map((r) => <option key={r}>{r}</option>)}
                    </select>
                  )}
                </td>
                <td className="py-2 pr-4">
                  {isProtected ? (
                    <span className="text-xs text-muted-foreground">protegido</span>
                  ) : (
                    <button
                      onClick={() => handleToggleActive(u)}
                      className={`text-xs px-2 py-1 rounded ${u.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}
                    >
                      {u.is_active ? 'Activo' : 'Inactivo'}
                    </button>
                  )}
                </td>
                <td className="py-2 pr-4 text-muted-foreground">
                  {u.last_login_at ? new Date(u.last_login_at).toLocaleString('es') : '—'}
                </td>
                <td className="py-2">
                  <div className="flex items-center gap-2">
                    {editingPwd ? (
                      <>
                        <input
                          type="password"
                          value={pwdValue}
                          onChange={(e) => setPwdValue(e.target.value)}
                          placeholder="Nueva contraseña"
                          className="border rounded px-2 py-1 text-xs w-36"
                          autoFocus
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handlePwdSave(u.id)
                            if (e.key === 'Escape') cancelPwdEdit()
                          }}
                        />
                        <button
                          onClick={() => handlePwdSave(u.id)}
                          disabled={pwdSaving || !pwdValue.trim()}
                          className="p-1 rounded text-green-600 hover:bg-green-50 disabled:opacity-40"
                          title="Guardar contraseña"
                        >
                          <Check className="size-3.5" />
                        </button>
                        <button
                          onClick={cancelPwdEdit}
                          className="p-1 rounded text-muted-foreground hover:bg-muted"
                          title="Cancelar"
                        >
                          <X className="size-3.5" />
                        </button>
                      </>
                    ) : (
                      <>
                        {canChangePasswords && (
                          <button
                            onClick={() => startPwdEdit(u.id)}
                            className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted"
                            title="Cambiar contraseña"
                          >
                            <Key className="size-3.5" />
                          </button>
                        )}
                        {!isProtected && (
                          <button
                            onClick={() => handleDelete(u)}
                            className="text-xs text-destructive hover:underline"
                          >
                            Eliminar
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
