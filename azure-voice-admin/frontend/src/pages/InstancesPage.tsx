import { useNavigate } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { InstanceList } from '@/components/instances/InstanceList'
import { useApi } from '@/hooks/useApi'
import type { Instance } from '@/types'

export function InstancesPage() {
  const navigate = useNavigate()
  const { data: instances, loading, error, refetch } = useApi<Instance[]>('/api/instances')

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

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <div className="rounded-xl border bg-card px-8 py-6 text-center shadow-sm">
          <p className="text-muted-foreground">加载中...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center p-12">
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-8 py-6 text-center shadow-sm">
          <p className="text-destructive">加载失败: {error.message}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between gap-4">
        <div className="space-y-1">
          <h1 className="bg-gradient-to-r from-indigo-600 to-violet-500 bg-clip-text text-3xl font-bold tracking-tight text-transparent">
            实例管理
          </h1>
          <p className="text-sm text-muted-foreground">管理你的 Azure OpenAI 语音实例</p>
        </div>
        <Button
          onClick={() => navigate('/instances/new')}
          className="bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-md transition hover:from-indigo-700 hover:to-violet-700 hover:shadow-lg"
        >
          <Plus aria-hidden="true" />
          新建实例
        </Button>
      </div>
      <InstanceList instances={instances ?? []} onDelete={handleDelete} />
    </div>
  )
}
