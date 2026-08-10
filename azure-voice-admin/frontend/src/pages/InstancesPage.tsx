import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, LayoutGrid, List, Trash2, Download, Upload, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { InstanceCard } from '@/components/instances/InstanceCard'
import { ExportDialog } from '@/components/instances/ExportDialog'
import { ImportDialog } from '@/components/instances/ImportDialog'
import { useApi } from '@/hooks/useApi'
import { useSystemStatus } from '@/hooks/useSystemStatus'
import { cn } from '@/lib/utils'
import { TypeBadge } from '@/components/instances/TypeBadge'
import type { Instance, InstanceType } from '@/types'

type TypeFilter = InstanceType | 'all'
type ViewMode = 'card' | 'list'

const FILTER_OPTIONS: ReadonlyArray<{ value: TypeFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'voice', label: '语音' },
  { value: 'chat', label: '对话' },
  { value: 'image', label: '图像' },
  { value: 'translate', label: '翻译' },
  { value: 'transcribe', label: '转录' },
]

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDay = Math.floor(diffMs / 86400000)
  const diffHour = Math.floor(diffMs / 3600000)
  const diffMin = Math.floor(diffMs / 60000)
  if (diffDay > 0) return `${diffDay} 天前`
  if (diffHour > 0) return `${diffHour} 小时前`
  if (diffMin > 0) return `${diffMin} 分钟前`
  return '刚刚'
}

export function InstancesPage() {
  const navigate = useNavigate()
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')
  const [viewMode, setViewMode] = useState<ViewMode>('card')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [showExport, setShowExport] = useState(false)
  const [showImport, setShowImport] = useState(false)

  const url = typeFilter === 'all' ? '/api/instances' : `/api/instances?type=${typeFilter}`
  const { data: instances, loading, error, refetch } = useApi<Instance[]>(url)
  const systemStatus = useSystemStatus()

  const handleDelete = async (id: string) => {
    if (!confirm('确定要删除此实例吗？')) return
    const res = await fetch(`/api/instances/${id}`, { method: 'DELETE', credentials: 'include' })
    if (res.ok) refetch()
    else alert('删除失败')
  }

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return
    if (!confirm(`确定要删除选中的 ${selectedIds.size} 个实例吗？此操作不可撤销。`)) return
    const promises = [...selectedIds].map(id =>
      fetch(`/api/instances/${id}`, { method: 'DELETE', credentials: 'include' })
    )
    await Promise.all(promises)
    setSelectedIds(new Set())
    refetch()
  }

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (!instances) return
    if (selectedIds.size === instances.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(instances.map(i => i.id)))
    }
  }

  const list = instances ?? []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="bg-gradient-to-r from-indigo-600 to-violet-500 bg-clip-text text-3xl font-bold tracking-tight text-transparent">
            实例管理
          </h1>
          <p className="text-sm text-muted-foreground">管理你的 Azure OpenAI 测试实例</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setShowImport(true)}>
            <Upload className="h-4 w-4" />
            导入
          </Button>
          <Button variant="outline" onClick={() => setShowExport(true)} disabled={selectedIds.size === 0}>
            <Download className="h-4 w-4" />
            导出{selectedIds.size > 0 ? ` (${selectedIds.size})` : ''}
          </Button>
          <Button
            onClick={() => navigate('/instances/new')}
            className="bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-md transition hover:from-indigo-700 hover:to-violet-700 hover:shadow-lg"
          >
            <Plus aria-hidden="true" />
            新建实例
          </Button>
        </div>
      </div>

      {/* AVX2 Warning */}
      {systemStatus && !systemStatus.realtime_available && (
        <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600" />
          <div className="text-sm">
            <p className="font-medium text-amber-800">实时功能不可用</p>
            <p className="text-amber-700">当前服务器 CPU 不支持 AVX2 指令集，语音对话、实时翻译和实时转录功能无法使用。文本对话和图像生成功能正常。</p>
          </div>
        </div>
      )}

      {/* Filter + View Toggle */}
      <div className="flex items-center justify-between gap-4">
        <div className="inline-flex rounded-lg border bg-muted/40 p-1">
          {FILTER_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setTypeFilter(option.value)}
              className={cn(
                'rounded-md px-3 py-1.5 text-sm font-medium transition',
                typeFilter === option.value
                  ? 'bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div className="inline-flex rounded-lg border bg-muted/40 p-1">
          <button
            type="button"
            onClick={() => setViewMode('card')}
            className={cn('rounded-md p-1.5 transition', viewMode === 'card' ? 'bg-background shadow-sm' : 'text-muted-foreground hover:text-foreground')}
            title="卡片视图"
          >
            <LayoutGrid className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setViewMode('list')}
            className={cn('rounded-md p-1.5 transition', viewMode === 'list' ? 'bg-background shadow-sm' : 'text-muted-foreground hover:text-foreground')}
            title="列表视图"
          >
            <List className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Batch Actions Bar */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-2">
          <span className="text-sm font-medium">已选择 {selectedIds.size} 项</span>
          <Button size="sm" variant="destructive" onClick={handleBatchDelete}>
            <Trash2 className="h-4 w-4" />
            批量删除
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelectedIds(new Set())}>
            取消选择
          </Button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center p-12">
          <p className="text-muted-foreground">加载中...</p>
        </div>
      ) : error ? (
        <div className="flex items-center justify-center p-12">
          <p className="text-destructive">加载失败: {error.message}</p>
        </div>
      ) : list.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed p-14 text-center">
          <p className="text-muted-foreground">还没有配置实例，点击上方按钮创建第一个实例</p>
        </div>
      ) : viewMode === 'card' ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((instance) => (
            <div key={instance.id} className="relative">
              <input
                type="checkbox"
                checked={selectedIds.has(instance.id)}
                onChange={() => toggleSelect(instance.id)}
                className="absolute left-3 top-3 z-10 h-4 w-4 rounded border-gray-300"
                aria-label={`选择 ${instance.name}`}
              />
              <InstanceCard instance={instance} onDelete={handleDelete} />
            </div>
          ))}
        </div>
      ) : (
        /* List/Table View */
        <div className="rounded-xl border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/50">
              <tr>
                <th className="w-10 px-4 py-3">
                  <input
                    type="checkbox"
                    checked={list.length > 0 && selectedIds.size === list.length}
                    onChange={toggleSelectAll}
                    className="h-4 w-4 rounded border-gray-300"
                    aria-label="全选"
                  />
                </th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">名称</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">类型</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">端点</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">部署</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">创建时间</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">操作</th>
              </tr>
            </thead>
            <tbody>
              {list.map((instance) => (
                <tr key={instance.id} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(instance.id)}
                      onChange={() => toggleSelect(instance.id)}
                      className="h-4 w-4 rounded border-gray-300"
                      aria-label={`选择 ${instance.name}`}
                    />
                  </td>
                  <td className="px-4 py-3 font-medium">{instance.name}</td>
                  <td className="px-4 py-3"><TypeBadge type={instance.type} /></td>
                  <td className="px-4 py-3 max-w-[200px] truncate font-mono text-xs" title={instance.endpoint}>{instance.endpoint}</td>
                  <td className="px-4 py-3 font-mono text-xs">{instance.deployment}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{formatRelativeTime(instance.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      <Button size="sm" variant="outline" onClick={() => navigate(`/instances/${instance.id}`)}>编辑</Button>
                      <Button size="sm" variant="destructive" onClick={() => handleDelete(instance.id)}>删除</Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Dialogs */}
      <ExportDialog
        open={showExport}
        onClose={() => setShowExport(false)}
        instances={list.filter(i => selectedIds.has(i.id)).map(i => ({ id: i.id, name: i.name, type: i.type }))}
      />
      <ImportDialog
        open={showImport}
        onClose={() => setShowImport(false)}
        onSuccess={refetch}
      />
    </div>
  )
}
