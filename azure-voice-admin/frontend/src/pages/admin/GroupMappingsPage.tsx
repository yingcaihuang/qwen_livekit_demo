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

interface AuthentikStep {
  step: number
  title: string
  desc: string
  details?: string[]
  code?: string
  afterCode?: string[]
}

const AUTHENTIK_STEPS: AuthentikStep[] = [
  {
    step: 1,
    title: '在 Authentik 中创建组',
    desc: '进入 Authentik 管理后台 → Directory → Groups → Create Group',
    details: [
      '组名建议使用英文，如 platform-admins、ai-testers、viewers',
      '组名需与本页面"添加映射"中填写的名称完全一致（区分大小写）',
    ],
  },
  {
    step: 2,
    title: '将用户分配到对应组',
    desc: '点击组名进入详情页 → Members 选项卡 → Add existing user',
    details: [
      '一个用户可以属于多个组，系统会取所有匹配角色的并集',
      '修改组成员后，用户下次 SSO 登录时角色会自动更新',
    ],
  },
  {
    step: 3,
    title: '创建 Scope Mapping（确保 groups claim 可用）',
    desc: '进入 Customization → Property Mappings → Create → Scope Mapping',
    details: [
      'Mapping Name（名称）: 填 groups（或任意名称如 "Groups Claim"）',
      '作用域名称（Scope Name）: 填 groups',
      '描述: 可留空或填 "Returns user group names"',
      '表达式（Expression）: 填入以下 Python 代码:',
    ],
    code: 'return [group.name for group in request.user.ak_groups.all()]',
    afterCode: [
      '点击 Create 保存',
      '然后进入 Applications → Providers → 编辑你的 OAuth2 Provider',
      '在 "Scopes" / "Property Mappings" 区域，将刚才创建的 groups mapping 添加进去',
      '确保 SSO 配置页的 Scopes 字段包含 "groups"（默认已包含）',
    ],
  },
  {
    step: 4,
    title: '在本页面创建组→角色映射',
    desc: '在下方"添加映射"表单中操作',
    details: [
      'Authentik 组名: 填写与 Authentik 中完全一致的组名（如 platform-admins）',
      '映射角色: 选择该组对应的平台权限级别',
      '  • super_admin — 全部权限 + 用户/SSO管理',
      '  • admin — 管理实例 + 查看所有人的数据',
      '  • tester — 使用测试功能 + 管理自己的数据',
      '  • viewer — 只读，查看自己的数据',
    ],
  },
  {
    step: 5,
    title: 'SSO 用户登录时自动匹配',
    desc: '无需额外操作，系统自动处理',
    details: [
      '用户通过"统一认证入口"登录时，系统从 ID Token 的 groups claim 读取组列表',
      '根据本页面配置的映射关系自动计算角色',
      '再次登录时如果组发生变化，角色会自动更新（收敛）',
    ],
  },
  {
    step: 6,
    title: '默认角色（未匹配时）',
    desc: '未匹配到任何映射的 SSO 用户自动获得 viewer 角色',
    details: [
      '如果用户不属于任何已配置映射的组，系统默认赋予 viewer（只读）权限',
      '确保至少为管理员组创建了映射，否则所有 SSO 用户都只有只读权限',
    ],
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
            <div className="space-y-4">
              {AUTHENTIK_STEPS.map((s) => (
                <div key={s.step} className="flex gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                    {s.step}
                  </span>
                  <div className="space-y-1.5 flex-1">
                    <p className="text-sm font-semibold text-blue-900">{s.title}</p>
                    <p className="text-xs text-blue-700/80">{s.desc}</p>
                    {s.details && (
                      <ul className="space-y-0.5 text-xs text-blue-800/70">
                        {s.details.map((d, i) => (
                          <li key={i} className={d.startsWith('  •') ? 'pl-4' : ''}>
                            {d.startsWith('  •') ? d : `• ${d}`}
                          </li>
                        ))}
                      </ul>
                    )}
                    {s.code && (
                      <pre className="rounded-md bg-gray-900 px-3 py-2 text-xs text-green-300 font-mono overflow-x-auto">
                        {s.code}
                      </pre>
                    )}
                    {s.afterCode && (
                      <ul className="space-y-0.5 text-xs text-blue-800/70">
                        {s.afterCode.map((d, i) => (
                          <li key={i}>• {d}</li>
                        ))}
                      </ul>
                    )}
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
