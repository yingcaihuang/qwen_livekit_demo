import { useEffect, useState } from 'react'

interface User { id: string; username: string; email: string | null; auth_source: string; is_active: boolean; must_change_password: boolean; roles: string[]; created_at: string }

const VALID_ROLES = ['super_admin', 'admin', 'tester', 'viewer']

export function UsersPage() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', password: '', email: '', roles: ['viewer'] })
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  const loadUsers = () => {
    fetch('/api/admin/users', { credentials: 'include' })
      .then(r => r.json()).then(setUsers).catch(() => {}).finally(() => setLoading(false))
  }
  useEffect(() => { loadUsers() }, [])

  const handleCreate = async () => {
    setCreating(true); setError('')
    const res = await fetch('/api/admin/users', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
      body: JSON.stringify(newUser),
    })
    if (res.ok) { setShowCreate(false); setNewUser({ username: '', password: '', email: '', roles: ['viewer'] }); loadUsers() }
    else { const d = await res.json().catch(() => ({})); setError(d.detail || '创建失败') }
    setCreating(false)
  }

  const toggleActive = async (u: User) => {
    await fetch(`/api/admin/users/${u.id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
      body: JSON.stringify({ is_active: !u.is_active }),
    })
    loadUsers()
  }

  const changeRole = async (u: User, role: string) => {
    await fetch(`/api/admin/users/${u.id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
      body: JSON.stringify({ roles: [role] }),
    })
    loadUsers()
  }

  if (loading) return <div className="p-6">加载中...</div>

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">用户管理</h2>
        <button onClick={() => setShowCreate(true)} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">添加用户</button>
      </div>

      {showCreate && (
        <div className="rounded-lg border p-4 space-y-3">
          <h3 className="font-medium">创建本地账号</h3>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <input placeholder="用户名" value={newUser.username} onChange={e => setNewUser(u => ({...u, username: e.target.value}))} className="rounded-md border px-3 py-1.5 text-sm" />
            <input placeholder="密码" type="password" value={newUser.password} onChange={e => setNewUser(u => ({...u, password: e.target.value}))} className="rounded-md border px-3 py-1.5 text-sm" />
            <select value={newUser.roles[0]} onChange={e => setNewUser(u => ({...u, roles: [e.target.value]}))} className="rounded-md border px-3 py-1.5 text-sm">
              {VALID_ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-2">
            <button onClick={handleCreate} disabled={creating} className="rounded bg-primary px-4 py-1.5 text-sm text-primary-foreground disabled:opacity-50">{creating ? '创建中...' : '创建'}</button>
            <button onClick={() => setShowCreate(false)} className="rounded border px-4 py-1.5 text-sm">取消</button>
          </div>
        </div>
      )}

      <div className="rounded-lg border">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/50">
            <tr><th className="px-4 py-2 text-left">用户名</th><th className="px-4 py-2 text-left">来源</th><th className="px-4 py-2 text-left">角色</th><th className="px-4 py-2 text-left">状态</th><th className="px-4 py-2 text-left">操作</th></tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className="border-b last:border-0">
                <td className="px-4 py-2">{u.username}</td>
                <td className="px-4 py-2">{u.auth_source}</td>
                <td className="px-4 py-2">
                  <select value={u.roles[0] || 'viewer'} onChange={e => changeRole(u, e.target.value)} className="rounded border px-2 py-0.5 text-xs">
                    {VALID_ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                <td className="px-4 py-2">{u.is_active ? '✅ 启用' : '❌ 禁用'}</td>
                <td className="px-4 py-2">
                  <button onClick={() => toggleActive(u)} className="text-xs text-blue-600 hover:underline">
                    {u.is_active ? '禁用' : '启用'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
