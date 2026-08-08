import { useEffect, useState } from 'react'

interface Mapping { id: string; group_name: string; role: string; created_at: string }

export function GroupMappingsPage() {
  const [mappings, setMappings] = useState<Mapping[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/admin/group-mappings', { credentials: 'include' })
      .then(r => r.json()).then(setMappings).catch(() => {}).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-6">加载中...</div>

  return (
    <div className="space-y-6 p-6">
      <h2 className="text-xl font-bold">组→角色映射</h2>
      <div className="rounded-lg border">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/50">
            <tr><th className="px-4 py-2 text-left">Authentik 组名</th><th className="px-4 py-2 text-left">平台角色</th></tr>
          </thead>
          <tbody>
            {mappings.length === 0 ? (
              <tr><td colSpan={2} className="px-4 py-4 text-center text-muted-foreground">暂无映射配置</td></tr>
            ) : mappings.map(m => (
              <tr key={m.id} className="border-b last:border-0">
                <td className="px-4 py-2">{m.group_name}</td>
                <td className="px-4 py-2">{m.role}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
