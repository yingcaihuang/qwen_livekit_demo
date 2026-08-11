import { Fragment, useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Search, Filter } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

interface AuditLog {
  id: number
  timestamp: string
  user_id: string | null
  username: string | null
  method: string
  path: string
  status_code: number
  ip_address: string | null
  duration_ms: number | null
  request_body: string | null
  detail: string | null
}

interface AuditResponse {
  items: AuditLog[]
  total: number
  page: number
  page_size: number
}

const METHOD_COLORS: Record<string, string> = {
  GET: 'bg-blue-100 text-blue-700',
  POST: 'bg-emerald-100 text-emerald-700',
  PUT: 'bg-amber-100 text-amber-700',
  PATCH: 'bg-purple-100 text-purple-700',
  DELETE: 'bg-red-100 text-red-700',
}

function StatusBadge({ code }: { code: number }) {
  const color = code < 300 ? 'text-emerald-600' : code < 400 ? 'text-blue-600' : code < 500 ? 'text-amber-600' : 'text-red-600'
  return <span className={cn('font-mono text-xs font-semibold', color)}>{code}</span>
}

export function AuditPage() {
  const [data, setData] = useState<AuditResponse | null>(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [pathFilter, setPathFilter] = useState('')
  const [methodFilter, setMethodFilter] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const fetchLogs = (p: number) => {
    setLoading(true)
    const params = new URLSearchParams({ page: String(p), page_size: '50' })
    if (pathFilter) params.set('path_contains', pathFilter)
    if (methodFilter) params.set('method', methodFilter)

    fetch(`/api/admin/audit?${params}`, { credentials: 'include' })
      .then(r => r.json())
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchLogs(page) }, [page])

  const handleSearch = () => { setPage(1); fetchLogs(1) }

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="bg-gradient-to-r from-indigo-600 to-violet-500 bg-clip-text text-3xl font-bold tracking-tight text-transparent">
          审计日志
        </h1>
        <p className="text-sm text-muted-foreground">
          记录所有 API 操作，支持按路径、方法筛选
        </p>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="flex items-center gap-3 py-3">
          <div className="flex items-center gap-2 flex-1">
            <Search className="h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="按路径筛选（如 /api/instances）"
              value={pathFilter}
              onChange={e => setPathFilter(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              className="h-8 max-w-xs"
            />
          </div>
          <select
            value={methodFilter}
            onChange={e => setMethodFilter(e.target.value)}
            className="h-8 rounded-md border px-2 text-xs"
          >
            <option value="">全部方法</option>
            <option value="GET">GET</option>
            <option value="POST">POST</option>
            <option value="PUT">PUT</option>
            <option value="DELETE">DELETE</option>
            <option value="PATCH">PATCH</option>
          </select>
          <Button size="sm" onClick={handleSearch}>
            <Filter className="h-3.5 w-3.5" />
            筛选
          </Button>
          <span className="text-xs text-muted-foreground">共 {data?.total ?? 0} 条</span>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center p-12">
              <p className="text-muted-foreground">加载中...</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/50">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">时间</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">用户</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">方法</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">路径</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">状态</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">IP</th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">耗时</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items.map(log => (
                    <Fragment key={log.id}>
                      <tr
                        className="border-b last:border-0 hover:bg-muted/30 cursor-pointer transition-colors"
                        onClick={() => setExpandedId(expandedId === log.id ? null : log.id)}
                      >
                        <td className="px-4 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                          {new Date(log.timestamp + 'Z').toLocaleString('zh-CN')}
                        </td>
                        <td className="px-4 py-2.5 text-xs font-medium">
                          {log.username || <span className="text-muted-foreground">-</span>}
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-bold', METHOD_COLORS[log.method] || 'bg-gray-100')}>
                            {log.method}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 font-mono text-xs max-w-[300px] truncate" title={log.path}>
                          {log.path}
                        </td>
                        <td className="px-4 py-2.5"><StatusBadge code={log.status_code} /></td>
                        <td className="px-4 py-2.5 text-xs text-muted-foreground">{log.ip_address || '-'}</td>
                        <td className="px-4 py-2.5 text-xs text-muted-foreground">
                          {log.duration_ms != null ? `${log.duration_ms}ms` : '-'}
                        </td>
                      </tr>
                      {expandedId === log.id && log.request_body && (
                        <tr className="bg-muted/20">
                          <td colSpan={7} className="px-6 py-3">
                            <p className="text-xs font-medium text-muted-foreground mb-1">请求体：</p>
                            <pre className="text-xs bg-background rounded p-2 border overflow-x-auto max-h-40">
                              {(() => { try { return JSON.stringify(JSON.parse(log.request_body), null, 2) } catch { return log.request_body } })()}
                            </pre>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm text-muted-foreground">
            第 {page} / {totalPages} 页
          </span>
          <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  )
}
