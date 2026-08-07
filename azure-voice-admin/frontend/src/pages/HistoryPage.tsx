import { useState, useEffect, useCallback } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SessionList } from '@/components/history/SessionList'
import type { Instance, PaginatedSessions } from '@/types'

const PAGE_SIZE = 10

export function HistoryPage() {
  const [page, setPage] = useState(1)
  const [instanceFilter, setInstanceFilter] = useState<string>('')
  const [instances, setInstances] = useState<Instance[]>([])
  const [sessionsData, setSessionsData] = useState<PaginatedSessions | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Fetch instances for filter dropdown
  useEffect(() => {
    fetch('/api/instances')
      .then((res) => res.json())
      .then((data) => setInstances(data))
      .catch(() => {})
  }, [])

  // Fetch sessions with pagination and filter
  const fetchSessions = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(PAGE_SIZE),
      })
      if (instanceFilter) {
        params.set('instance_id', instanceFilter)
      }
      const response = await fetch(`/api/sessions?${params}`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
      const data = (await response.json()) as PaginatedSessions
      setSessionsData(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, instanceFilter])

  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  const handleDelete = async (id: string) => {
    if (!confirm('确定要删除此会话记录吗？此操作不可撤销。')) return
    try {
      const response = await fetch(`/api/sessions/${id}`, { method: 'DELETE' })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        const message = body?.detail || `删除失败 (${response.status})`
        alert(message)
        return
      }
      fetchSessions()
    } catch {
      alert('删除请求失败，请检查网络连接')
    }
  }

  const handleFilterChange = (value: string) => {
    setInstanceFilter(value)
    setPage(1)
  }

  const totalPages = sessionsData ? Math.ceil(sessionsData.total / PAGE_SIZE) : 0

  if (error) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-destructive">加载失败: {error}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">会话历史</h1>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-4">
        <label htmlFor="instance-filter" className="text-sm font-medium text-muted-foreground">
          按实例筛选:
        </label>
        <select
          id="instance-filter"
          value={instanceFilter}
          onChange={(e) => handleFilterChange(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
        >
          <option value="">全部实例</option>
          {instances.map((instance) => (
            <option key={instance.id} value={instance.id}>
              {instance.name}
            </option>
          ))}
        </select>
      </div>

      {/* Session List */}
      {loading ? (
        <div className="flex items-center justify-center p-12">
          <p className="text-muted-foreground">加载中...</p>
        </div>
      ) : (
        <SessionList sessions={sessionsData?.items ?? []} onDelete={handleDelete} />
      )}

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            共 {sessionsData?.total ?? 0} 条记录，第 {page}/{totalPages} 页
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft className="h-4 w-4" />
              上一页
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
