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
        <p className="text-muted-foreground">加载中...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-destructive">加载失败: {error.message}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">实例管理</h1>
        <Button onClick={() => navigate('/instances/new')}>
          <Plus />
          新建实例
        </Button>
      </div>
      <InstanceList instances={instances ?? []} onDelete={handleDelete} />
    </div>
  )
}
