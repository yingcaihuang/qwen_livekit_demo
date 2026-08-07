import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { InstanceList } from '@/components/instances/InstanceList'
import { useApi } from '@/hooks/useApi'
import { cn } from '@/lib/utils'
import type { Instance, InstanceType } from '@/types'

type TypeFilter = InstanceType | 'all'

const FILTER_OPTIONS: ReadonlyArray<{ value: TypeFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'voice', label: '语音' },
  { value: 'chat', label: '对话' },
  { value: 'image', label: '图像' },
]

export function InstancesPage() {
  const navigate = useNavigate()
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')
  const url =
    typeFilter === 'all'
      ? '/api/instances'
      : `/api/instances?type=${typeFilter}`
  const { data: instances, loading, error, refetch } = useApi<Instance[]>(url)

  const handleDelete = async (id: string) => {
    if (!confirm('确定要删除此实例吗？')) return
    try {
      const response = await fetch(`/api/instances/${id}`, { method: 'DELETE' })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        const message = body?.detail || `删除失败 (${response.status})`
        alert(message)
        return
      }
      refetch()
    } catch {
      alert('删除请求失败，请检查网络连接')
    }
  }

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
        <Button
          onClick={() => navigate('/instances/new')}
          className="bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-md transition hover:from-indigo-700 hover:to-violet-700 hover:shadow-lg"
        >
          <Plus aria-hidden="true" />
          新建实例
        </Button>
      </div>

      {/* Type filter (segmented control) */}
      <div className="inline-flex rounded-lg border bg-muted/40 p-1">
        {FILTER_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={typeFilter === option.value}
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

      {loading ? (
        <div className="flex items-center justify-center p-12">
          <div className="rounded-xl border bg-card px-8 py-6 text-center shadow-sm">
            <p className="text-muted-foreground">加载中...</p>
          </div>
        </div>
      ) : error ? (
        <div className="flex items-center justify-center p-12">
          <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-8 py-6 text-center shadow-sm">
            <p className="text-destructive">加载失败: {error.message}</p>
          </div>
        </div>
      ) : (
        <InstanceList instances={instances ?? []} onDelete={handleDelete} />
      )}
    </div>
  )
}
