import { useEffect, useState } from 'react'

interface Mapping { id: string; group_name: string; role: string; created_at: string }
const VALID_ROLES = ['super_admin', 'admin', 'tester', 'viewer']

export function GroupMappingsPage() {
  const [mappings, setMappings] = useState<Mapping[]>([])
  const [loading, setLoading] = useState(true)
  const [newGroup, setNewGroup] = useState('')
  const [newRole, setNewRole] = useState('viewer')
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState('')

  const load = () => {
    fetch('/api/admin/group-mappings', { credentials: 'include' })
      .then(r => r.json()).then(setMappings).catch(() => {}).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  const handleAdd = async () => {
    if (!newGroup.trim()) return
    setAdding(true); setError('')
    const res = await fetch('/api/admin/group-mappings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
      body: JSON.stringify({ group_name: newGroup.trim(), role: newRole }),
    })
    if (res.ok) { setNewGroup(''); load() }
    else { const d = await res.json().catch(() => ({})); setError(d.detail || '添加失败') }
    setAdding(false)
  }

  const handleDelete = async (id: string) => {
    await fetch(`/api/admin/group-mappings/${id}`, { method: 'DELETE', credentials: 'include' })
    load()
  }

  if (loading) return <div className="p-6">加载中...</div>

  return (
    <div className="space-y-6 p-6">
      <h2 className="text-xl font-bold">组 → 角色映射</h2>

      <div className="flex items-end gap-3 rounded-lg border p-4">
        <div className="flex-1">
          <label className="block text-sm font-medium text-gray-700">Authentik 组名</label>
          <input value={newGroup} onChange={e => setNewGroup(e.target.value)} placeholder="例如: platform-admins" className="mt-1 w-full rounded-md border px-3 py-1.5 text-sm" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700">映射角色</label>
          <select value={newRole} onChange={e => setNewRole(e.target.value)} className="mt-1 rounded-md border px-3 py-1.5 text-sm">
            {VALID_ROLES.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <button onClick={handleAdd} disabled={adding} className="rounded-lg bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
          {adding ? '添加中...' : '添加'}
        </button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="rounded-lg border">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/50">
            <tr><th className="px-4 py-2 text-left">Authentik 组名</th><th className="px-4 py-2 text-left">平台角色</th><th className="px-4 py-2 text-left">操作</th></tr>
          </thead>
          <tbody>
            {mappings.length === 0 ? (
              <tr><td colSpan={3} className="px-4 py-4 text-center text-muted-foreground">暂无映射，请在上方添加</td></tr>
            ) : mappings.map(m => (
              <tr key={m.id} className="border-b last:border-0">
                <td className="px-4 py-2 font-mono text-xs">{m.group_name}</td>
                <td className="px-4 py-2">{m.role}</td>
                <td className="px-4 py-2">
                  <button onClick={() => handleDelete(m.id)} className="text-xs text-red-600 hover:underline">删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
