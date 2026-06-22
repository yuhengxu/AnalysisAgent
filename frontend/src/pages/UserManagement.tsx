import { useCallback, useEffect, useState } from 'react'
import {
  createUser,
  deleteUser as apiDeleteUser,
  getUserPageOptions,
  listUsers,
  resetUserPassword,
  updateUser,
  type ManagedUser,
  type UserPageOption,
} from '../api/client'

export default function UserManagement() {
  const [users, setUsers] = useState<ManagedUser[]>([])
  const [pageOptions, setPageOptions] = useState<UserPageOption[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [newUsername, setNewUsername] = useState('')
  const [newAllowedPages, setNewAllowedPages] = useState<string[]>([])
  const [editPages, setEditPages] = useState<Record<number, string[]>>({})
  const [editActive, setEditActive] = useState<Record<number, boolean>>({})
  const [creating, setCreating] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [userList, options] = await Promise.all([listUsers(), getUserPageOptions()])
      setUsers(userList)
      setPageOptions(options)
      const pages: Record<number, string[]> = {}
      const active: Record<number, boolean> = {}
      for (const u of userList) {
        pages[u.id] = [...u.allowed_pages]
        active[u.id] = u.is_active
      }
      setEditPages(pages)
      setEditActive(active)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const togglePage = (pages: string[], key: string, checked: boolean) => {
    if (checked) return [...pages, key]
    return pages.filter((p) => p !== key)
  }

  const handleCreate = async () => {
    const username = newUsername.trim()
    if (!username) {
      setError('请输入用户名')
      return
    }
    setCreating(true)
    setError('')
    try {
      await createUser({ username, allowed_pages: newAllowedPages })
      setNewUsername('')
      setNewAllowedPages([])
      await load()
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : '创建失败')
      setError(String(msg))
    } finally {
      setCreating(false)
    }
  }

  const handleSave = async (u: ManagedUser) => {
    setError('')
    try {
      await updateUser(u.id, {
        allowed_pages: editPages[u.id],
        is_active: editActive[u.id],
      })
      await load()
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : '保存失败')
      setError(String(msg))
    }
  }

  const handleResetPassword = async (u: ManagedUser) => {
    if (!window.confirm(`确定将 ${u.username} 的密码重置为 qwer1234？`)) return
    setError('')
    try {
      await resetUserPassword(u.id)
      alert(`已重置 ${u.username} 的密码为 qwer1234`)
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : '重置失败')
      setError(String(msg))
    }
  }

  const handleDelete = async (u: ManagedUser) => {
    if (!window.confirm(`确定删除用户 ${u.username}？`)) return
    setError('')
    try {
      await apiDeleteUser(u.id)
      await load()
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (e instanceof Error ? e.message : '删除失败')
      setError(String(msg))
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-white/60">加载中…</div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">用户管理</h1>
        <p className="text-sm text-white/60">新增用户、分配页面权限、重置初始密码</p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="glass rounded-2xl p-5 space-y-4">
        <h2 className="text-lg font-medium">新增用户</h2>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="mb-1 block text-xs text-white/50">用户名</label>
            <input
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              placeholder="请输入用户名"
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-brand-red/50"
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          {pageOptions.map((p) => (
            <label key={p.key} className="flex items-center gap-2 text-sm text-white/80">
              <input
                type="checkbox"
                checked={newAllowedPages.includes(p.key)}
                onChange={(e) =>
                  setNewAllowedPages(togglePage(newAllowedPages, p.key, e.target.checked))
                }
                className="rounded"
              />
              {p.label}
            </label>
          ))}
        </div>
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={handleCreate}
            disabled={creating}
            className="rounded-lg bg-brand-red/80 px-4 py-2 text-sm hover:bg-brand-red disabled:opacity-50"
          >
            {creating ? '创建中…' : '创建用户'}
          </button>
          <p className="text-xs text-white/50">初始密码：qwer1234</p>
        </div>
      </div>

      <div className="glass rounded-2xl p-5 space-y-4">
        <h2 className="text-lg font-medium">用户列表</h2>
        {users.length === 0 ? (
          <p className="text-sm text-white/50">暂无用户</p>
        ) : (
          <div className="space-y-6">
            {users.map((u) => {
              const isAdmin = u.role === 'admin'
              const pages = editPages[u.id] ?? u.allowed_pages
              return (
                <div
                  key={u.id}
                  className="rounded-xl border border-white/10 bg-white/5 p-4 space-y-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{u.username}</span>
                      <span className="rounded-full bg-white/10 px-2 py-0.5 text-xs text-white/60">
                        {isAdmin ? '管理员' : '普通用户'}
                      </span>
                      {!isAdmin && (
                        <label className="flex items-center gap-1.5 text-xs text-white/60">
                          <input
                            type="checkbox"
                            checked={editActive[u.id] ?? u.is_active}
                            onChange={(e) =>
                              setEditActive((prev) => ({ ...prev, [u.id]: e.target.checked }))
                            }
                          />
                          启用
                        </label>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={isAdmin}
                        onClick={() => handleSave(u)}
                        className="rounded-lg bg-white/10 px-3 py-1.5 text-xs hover:bg-white/15 disabled:opacity-40"
                      >
                        保存权限
                      </button>
                      <button
                        type="button"
                        disabled={isAdmin}
                        onClick={() => handleResetPassword(u)}
                        className="rounded-lg bg-white/10 px-3 py-1.5 text-xs hover:bg-white/15 disabled:opacity-40"
                      >
                        重置密码
                      </button>
                      <button
                        type="button"
                        disabled={isAdmin}
                        onClick={() => handleDelete(u)}
                        className="rounded-lg bg-red-500/20 px-3 py-1.5 text-xs text-red-300 hover:bg-red-500/30 disabled:opacity-40"
                      >
                        删除
                      </button>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-3">
                    {pageOptions.map((p) => (
                      <label key={p.key} className="flex items-center gap-2 text-sm text-white/80">
                        <input
                          type="checkbox"
                          disabled={isAdmin}
                          checked={isAdmin || pages.includes(p.key)}
                          onChange={(e) =>
                            setEditPages((prev) => ({
                              ...prev,
                              [u.id]: togglePage(pages, p.key, e.target.checked),
                            }))
                          }
                          className="rounded"
                        />
                        {p.label}
                      </label>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
