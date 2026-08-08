import { useEffect, useState } from 'react'

interface User { id: string; username: string; email: string | null; auth_source: string; is_active: boolean; roles: string[]; created_at: string }

export function UsersPage() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/admin/users', { credentials: 'include' })
      .then(r => r.json()).then(setUsers).catch(() => {}).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-6">加载中...</div>

  return (
    <div className="space-y-6 p-6">
      <h2 className="text-xl font-bold">用户管理</h2>
      <div className="rounded-lg border">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/50">
            <tr><th className="px-4 py-2 text-left">用户名</th><th className="px-4 py-2 text-left">来源</th><th className="px-4 py-2 text-left">角色</th><th className="px-4 py-2 text-left">状态</th></tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className="border-b last:border-0">
                <td className="px-4 py-2">{u.username}</td>
                <td className="px-4 py-2">{u.auth_source}</td>
                <td className="px-4 py-2">{u.roles.join(', ')}</td>
                <td className="px-4 py-2">{u.is_active ? '✅ 启用' : '❌ 禁用'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
