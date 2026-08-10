import { useEffect, useState } from 'react'
import { Plus, UserPlus, Trash2, Ban, CheckCircle, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface User {
  id: string
  username: string
  email: string | null
  auth_source: string
  is_active: boolean
  must_change_password: boolean
  role_override: boolean
  roles: string[]
  groups: string[]
  created_at: string
}

const VALID_ROLES = ['super_admin', 'admin', 'tester', 'viewer']

const ROLE_COLORS: Record<string, string> = {
  super_admin: 'bg-rose-500/15 text-rose-700 border-rose-200',
  admin: 'bg-violet-500/15 text-violet-700 border-violet-200',
  tester: 'bg-blue-500/15 text-blue-700 border-blue-200',
  viewer: 'bg-gray-500/15 text-gray-700 border-gray-200',
}

export function UsersPage() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', password: '', email: '', roles: ['viewer'] })
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [refreshing, setRefreshing] = useState(false)

  const loadUsers = () => {
    setRefreshing(true)
    fetch('/api/admin/users', { credentials: 'include' })
      .then((r) => r.json())
      .then((data) => {
        setUsers(data)
        setSelected(new Set())
      })
      .catch(() => {})
      .finally(() => {
        setLoading(false)
        setRefreshing(false)
      })
  }
  useEffect(() => {
    loadUsers()
  }, [])

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selected.size === users.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(users.map((u) => u.id)))
    }
  }

  const batchAction = async (action: 'disable' | 'enable' | 'delete') => {
    const ids = Array.from(selected)
    if (ids.length === 0) return

    const labels = { disable: '禁用', enable: '启用', delete: '删除' }
    if (!confirm(`确定要批量${labels[action]} ${ids.length} 个用户吗？${action === 'delete' ? '此操作不可撤销。' : ''}`)) return

    const res = await fetch(`/api/admin/users/batch/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ user_ids: ids }),
    })
    if (res.ok) {
      const data = await res.json()
      alert(`成功${labels[action]} ${data.affected} 个用户`)
      loadUsers()
    } else {
      alert('操作失败')
    }
  }

  const handleCreate = async () => {
    setCreating(true)
    setError('')
    const res = await fetch('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(newUser),
    })
    if (res.ok) {
      setShowCreate(false)
      setNewUser({ username: '', password: '', email: '', roles: ['viewer'] })
      loadUsers()
    } else {
      const d = await res.json().catch(() => ({}))
      setError(d.detail || '创建失败')
    }
    setCreating(false)
  }

  const toggleActive = async (u: User) => {
    await fetch(`/api/admin/users/${u.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ is_active: !u.is_active }),
    })
    loadUsers()
  }

  const handleDelete = async (u: User) => {
    if (!confirm(`确定要删除用户 "${u.username}" 吗？此操作不可撤销。`)) return
    const res = await fetch(`/api/admin/users/${u.id}`, {
      method: 'DELETE',
      credentials: 'include',
    })
    if (res.ok) {
      loadUsers()
    } else {
      const d = await res.json().catch(() => ({}))
      alert(d.detail || '删除失败')
    }
  }

  const changeRole = async (u: User, role: string) => {
    await fetch(`/api/admin/users/${u.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ roles: [role] }),
    })
    loadUsers()
  }

  const resetOverride = async (u: User) => {
    await fetch(`/api/admin/users/${u.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ role_override: false }),
    })
    loadUsers()
  }

  const resetPassword = async (u: User) => {
    if (!confirm(`确定要重置用户 "${u.username}" 的密码吗？将生成随机新密码。`)) return
    try {
      const res = await fetch(`/api/admin/users/${u.id}/reset-password`, {
        method: 'POST',
        credentials: 'include',
      })
      if (res.ok) {
        const data = await res.json()
        await navigator.clipboard.writeText(data.new_password)
        alert(`密码已重置并复制到剪贴板。\n\n新密码: ${data.new_password}\n\n用户下次登录需修改密码。`)
        loadUsers()
      } else {
        const d = await res.json().catch(() => ({}))
        alert(d.detail || '重置密码失败')
      }
    } catch {
      alert('网络错误')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-muted-foreground">加载中...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <h1 className="bg-gradient-to-r from-indigo-600 to-violet-500 bg-clip-text text-3xl font-bold tracking-tight text-transparent">
            用户管理
          </h1>
          <p className="text-sm text-muted-foreground">
            管理本地用户与 SSO 用户的角色和状态
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={loadUsers} disabled={refreshing}>
            <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
            {refreshing ? '刷新中...' : '刷新'}
          </Button>
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4" />
            添加用户
          </Button>
        </div>
      </div>

      {/* Batch Actions Toolbar */}
      {selected.size > 0 && (
        <Card className="border-indigo-200 bg-indigo-50/50">
          <CardContent className="flex items-center gap-3 py-3">
            <span className="text-sm font-medium text-indigo-700">
              已选择 {selected.size} 个用户
            </span>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => batchAction('disable')}
                className="text-amber-700 border-amber-300 hover:bg-amber-50"
              >
                <Ban className="mr-1 h-3.5 w-3.5" />
                批量禁用
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => batchAction('enable')}
                className="text-emerald-700 border-emerald-300 hover:bg-emerald-50"
              >
                <CheckCircle className="mr-1 h-3.5 w-3.5" />
                批量启用
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={() => batchAction('delete')}
              >
                <Trash2 className="mr-1 h-3.5 w-3.5" />
                批量删除
              </Button>
            </div>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setSelected(new Set())}
              className="ml-auto text-xs"
            >
              取消选择
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Create User Card */}
      {showCreate && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <UserPlus className="h-5 w-5 text-indigo-500" />
              创建本地账号
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
              <div className="space-y-2">
                <Label>用户名</Label>
                <Input
                  placeholder="用户名"
                  value={newUser.username}
                  onChange={(e) => setNewUser((u) => ({ ...u, username: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label>密码</Label>
                <Input
                  placeholder="密码"
                  type="password"
                  value={newUser.password}
                  onChange={(e) => setNewUser((u) => ({ ...u, password: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label>邮箱（可选）</Label>
                <Input
                  placeholder="user@example.com"
                  value={newUser.email}
                  onChange={(e) => setNewUser((u) => ({ ...u, email: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label>角色</Label>
                <select
                  value={newUser.roles[0]}
                  onChange={(e) => setNewUser((u) => ({ ...u, roles: [e.target.value] }))}
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  {VALID_ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
            <div className="mt-4 flex gap-2">
              <Button onClick={handleCreate} disabled={creating}>
                {creating ? '创建中...' : '创建'}
              </Button>
              <Button variant="outline" onClick={() => setShowCreate(false)}>
                取消
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Users Table Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">用户列表</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/50">
                <tr>
                  <th className="px-4 py-3 text-left">
                    <input
                      type="checkbox"
                      checked={selected.size === users.length && users.length > 0}
                      onChange={toggleSelectAll}
                      className="h-4 w-4 rounded border-gray-300"
                      aria-label="全选"
                    />
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">用户名</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">来源</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">角色</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">SSO 组</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">状态</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr
                    key={u.id}
                    className={cn(
                      'border-b last:border-0 transition-colors',
                      selected.has(u.id) ? 'bg-indigo-50/50' : 'hover:bg-muted/30'
                    )}
                  >
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selected.has(u.id)}
                        onChange={() => toggleSelect(u.id)}
                        className="h-4 w-4 rounded border-gray-300"
                        aria-label={`选择 ${u.username}`}
                      />
                    </td>
                    <td className="px-4 py-3 font-medium">{u.username}</td>
                    <td className="px-4 py-3">
                      <Badge variant="secondary" className="text-xs">
                        {u.auth_source}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <select
                          value={u.roles[0] || 'viewer'}
                          onChange={(e) => changeRole(u, e.target.value)}
                          className={cn(
                            'rounded-md border px-2 py-0.5 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
                            ROLE_COLORS[u.roles[0] ?? 'viewer'] || ROLE_COLORS.viewer
                          )}
                        >
                          {VALID_ROLES.map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </select>
                        {u.auth_source === 'sso' && u.role_override && (
                          <Badge variant="outline" className="text-xs border-amber-300 text-amber-700 bg-amber-50">
                            手动
                          </Badge>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {u.auth_source === 'sso' && u.groups.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {u.groups.map((g) => (
                            <Badge key={g} variant="outline" className="text-xs">
                              {g}
                            </Badge>
                          ))}
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1.5 text-xs">
                        <span
                          className={cn(
                            'inline-block h-2 w-2 rounded-full',
                            u.is_active ? 'bg-emerald-500' : 'bg-red-400'
                          )}
                        />
                        {u.is_active ? '启用' : '禁用'}
                      </span>
                    </td>
                    <td className="px-4 py-3 space-x-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => toggleActive(u)}
                        className={cn(
                          'text-xs',
                          u.is_active
                            ? 'text-destructive hover:text-destructive'
                            : 'text-emerald-600 hover:text-emerald-700'
                        )}
                      >
                        {u.is_active ? '禁用' : '启用'}
                      </Button>
                      {u.auth_source === 'sso' && u.role_override && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => resetOverride(u)}
                          className="text-xs text-amber-600 hover:text-amber-700"
                        >
                          解除覆盖
                        </Button>
                      )}
                      {u.auth_source === 'local' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => resetPassword(u)}
                          className="text-xs text-indigo-600 hover:text-indigo-700"
                        >
                          重置密码
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(u)}
                        className="text-xs text-destructive hover:text-destructive"
                      >
                        删除
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
