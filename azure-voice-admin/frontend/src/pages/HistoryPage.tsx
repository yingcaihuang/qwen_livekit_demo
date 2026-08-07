import { useState, useEffect, useCallback } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SessionList } from '@/components/history/SessionList'
import { HistoryFilter, type HistoryTypeFilter } from '@/components/history/HistoryFilter'
import type { Instance, HistoryItem, PaginatedHistory } from '@/types'

const PAGE_SIZE = 10

export function HistoryPage() {
  const [page, setPage] = useState(1)
  const [typeFilter, setTypeFilter] = useState<HistoryTypeFilter>('')
  const [instanceFilter, setInstanceFilter] = useState<string>('')
  const [instances, setInstances] = useState<Instance[]>([])
  const [historyData, setHistoryData] = useState<PaginatedHistory | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Fetch instances for the filter dropdown.
  useEffect(() => {
    fetch('/api/instances')
      .then((res) => res.json())
      .then((data) => setInstances(data))
      .catch(() => {})
  }, [])

  // Fetch unified history with pagination + type/instance filters.
  const fetchHistory = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(PAGE_SIZE),
      })
      if (typeFilter) {
        params.set('type', typeFilter)
      }
      if (instanceFilter) {
        params.set('instance_id', instanceFilter)
      }
      const response = await fetch(`/api/history?${params}`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
      const data = (await response.json()) as PaginatedHistory
      setHistoryData(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [page, typeFilter, instanceFilter])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

  const handleDelete = async (item: HistoryItem) => {
    if (!confirm('确定要删除此测试记录吗？此操作不可撤销。')) return
    // Route the delete to the correct endpoint based on the record type.
    const url =
      item.type === 'image' ? `/api/images/${item.id}` : `/api/sessions/${item.id}`
    try {
      const response = await fetch(url, { method: 'DELETE' })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        const message = body?.detail || `删除失败 (${response.status})`
        alert(message)
        return
      }
      fetchHistory()
    } catch {
      alert('删除请求失败，请检查网络连接')
    }
  }

  const handleTypeChange = (value: HistoryTypeFilter) => {
    setTypeFilter(value)
    setPage(1)
  }

  const handleInstanceChange = (value: string) => {
    setInstanceFilter(value)
    setPage(1)
  }

  const totalPages = historyData ? Math.ceil(historyData.total / PAGE_SIZE) : 0

  if (error) {
    return (
      <div className="flex items-center justify-center p-12">
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-8 py-6 text-center shadow-sm">
          <p className="text-destructive">加载失败: {error}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="space-y-1">
        <h1 className="bg-gradient-to-r from-indigo-600 to-violet-500 bg-clip-text text-3xl font-bold tracking-tight text-transparent">
          测试历史
        </h1>
        <p className="text-sm text-muted-foreground">查看语音 / 对话 / 图像测试记录与用量</p>
      </div>

      {/* Filters */}
      <HistoryFilter
        typeFilter={typeFilter}
        instanceFilter={instanceFilter}
        instances={instances}
        onTypeChange={handleTypeChange}
        onInstanceChange={handleInstanceChange}
      />

      {/* History List */}
      {loading ? (
        <div className="flex items-center justify-center p-12">
          <div className="rounded-xl border bg-card px-8 py-6 text-center shadow-sm">
            <p className="text-muted-foreground">加载中...</p>
          </div>
        </div>
      ) : (
        <SessionList items={historyData?.items ?? []} onDelete={handleDelete} />
      )}

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between rounded-xl border bg-card px-4 py-3 shadow-sm">
          <p className="text-sm text-muted-foreground">
            共 <span className="font-semibold text-foreground">{historyData?.total ?? 0}</span> 条记录，第{' '}
            <span className="font-semibold text-foreground">{page}</span>/{totalPages} 页
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
