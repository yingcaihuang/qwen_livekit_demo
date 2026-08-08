import { useEffect, useState } from 'react'
import { Info, Plus, Trash2, ChevronDown, ChevronUp } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface Mapping {
  id: string
  group_name: string
  role: string
  created_at: string
}

const VALID_ROLES = ['super_admin', 'admin', 'tester', 'viewer']

const ROLE_COLORS: Record<string, string> = {
  super_admin: 'bg-rose-500/15 text-rose-700 border-rose-200',
  admin: 'bg-violet-500/15 text-violet-700 border-violet-200',
  tester: 'bg-blue-500/15 text-blue-700 border-blue-200',
  viewer: 'bg-gray-500/15 text-gray-700 border-gray-200',
}

const AUTHENTIK_STEPS = [
  {
    step: 1,
    title: '在 Authentik 中创建组',
    desc: '进入 Directory → Groups，创建对应的组（例如 platform-admins、ai-testers）。',
  },
  {
    step: 2,
    title: '将用户分配到对应组',
    desc: '在组详情页 → Members 选项卡中，将需要的用户添加到该组。',
  },
  {
    step: 3,
    title: '确保 Scope Mapping 包含 groups claim',
    desc: '进入 Customization → Property Mappings，确认 Scope 中包含 groups claim，或新建一个返回用户组列表的 mapping。',
  },
  {
    step: 4,
    title: '在本页面创建映射',
    desc: '在下方表单中输入 Authentik 组名，选择对应的平台角色后点击添加。',
  },
  {
    step: 5,
    title: 'SSO 用户登录自动匹配',
    desc: 'SSO 用户首次登录时，系统会读取其 ID Token 中的 groups claim，自动根据映射分配角色。',
  },
  {
    step: 6,
    title: '默认角色',
    desc: '未匹配到任何组的 SSO 用户将自动获得 viewer（只读）角色。',
  },
]

export function GroupMappingsPage() {
  const [mappings, setMappings] = useState<Mapping[]>([])
  const [loading, setLoading] = useState(true)
  const [newGroup, setNewGroup] = useState('')
  const [newRole, setNewRole] = useState('viewer')
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState('')
  const [stepsOpen, setStepsOpen] = useState(false)

  const load = () => {
    fetch('/api/admin/group-mappings', { credentials: 'include' })
      .then((r) => r.json())
      .then(setMappings)
      .catch(() => {})
      .finally(() => setLoading(false))
  }
  useEffect(() => {
    load()
  }, [])

  const handleAdd = async () => {
    if (!newGroup.trim()) return
    setAdding(true)
    setError('')
    const res = await fetch('/api/admin/group-mappings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ group_name: newGroup.trim(), role: newRole }),
    })
    if (res.ok) {
      setNewGroup('')
      load()
    } else {
      const d = await res.json().catch(() => ({}))
      setError(d.detail || '添加失败')
    }
    setAdding(false)
  }

  const handleDelete = async (id: string) => {
    await fetch(`/api/admin/group-mappings/${id}`, { method: 'DELETE', credentials: 'include' })
    load()
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
      <div className="space-y-1">
        <h1 className="bg-gradient-to-r from-indigo-600 to-violet-500 bg-clip-text text-3xl font-bold tracking-tight text-transparent">
          组 → 角色映射
        </h1>
        <p className="text-sm text-muted-foreground">
          将 Authentik SSO 组映射到平台角色，用户登录时自动分配权限
        </p>
      </div>

      {/* Authentik Integration Guide */}
      <Card className="border-blue-200 bg-blue-50/50">
        <CardHeader className="pb-3">
          <button
            type="button"
            onClick={() => setStepsOpen(!stepsOpen)}
            className="flex w-full items-center justify-between"
          >
            <div className="flex items-center gap-2">
              <Info className="h-5 w-5 text-blue-600" />
              <CardTitle className="text-sm font-semibold text-blue-800">
                Authentik 配合步骤说明
              </CardTitle>
            </div>
            {stepsOpen ? (
              <ChevronUp className="h-4 w-4 text-blue-600" />
            ) : (
              <ChevronDown className="h-4 w-4 text-blue-600" />
            )}
          </button>
        </CardHeader>
        {stepsOpen && (
          <CardContent className="pt-0">
            <div className="space-y-3">
              {AUTHENTIK_STEPS.map((s) => (
                <div key={s.step} className="flex gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                    {s.step}
                  </span>
                  <div className="space-y-0.5">
                    <p className="text-sm font-medium text-blue-900">{s.title}</p>
                    <p className="text-xs text-blue-700/80">{s.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        )}
      </Card>

      {/* Add Mapping Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">添加映射</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <div className="flex-1 space-y-2">
              <Label>Authentik 组名</Label>
              <Input
                value={newGroup}
                onChange={(e) => setNewGroup(e.target.value)}
                placeholder="例如: platform-admins"
              />
            </div>
            <div className="w-full space-y-2 sm:w-44">
              <Label>映射角色</Label>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {VALID_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <Button onClick={handleAdd} disabled={adding || !newGroup.trim()}>
              <Plus className="h-4 w-4" />
              {adding ? '添加中...' : '添加'}
            </Button>
          </div>
          {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>

      {/* Mappings Table Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">当前映射</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/50">
                <tr>
                  <th className="px-6 py-3 text-left font-medium text-muted-foreground">
                    Authentik 组名
                  </th>
                  <th className="px-6 py-3 text-left font-medium text-muted-foreground">
                    平台角色
                  </th>
                  <th className="px-6 py-3 text-left font-medium text-muted-foreground">
                    操作
                  </th>
                </tr>
              </thead>
              <tbody>
                {mappings.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-6 py-8 text-center text-muted-foreground">
                      暂无映射，请在上方添加
                    </td>
                  </tr>
                ) : (
                  mappings.map((m) => (
                    <tr key={m.id} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                      <td className="px-6 py-3">
                        <code className="rounded bg-muted px-2 py-0.5 text-xs font-mono">
                          {m.group_name}
                        </code>
                      </td>
                      <td className="px-6 py-3">
                        <Badge
                          variant="outline"
                          className={cn('text-xs', ROLE_COLORS[m.role] || ROLE_COLORS.viewer)}
                        >
                          {m.role}
                        </Badge>
                      </td>
                      <td className="px-6 py-3">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDelete(m.id)}
                          className="text-destructive hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
                          删除
                        </Button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
