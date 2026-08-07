import { useState } from 'react'
import { Server, FlaskConical, MessageSquare, Zap, ArrowUp, ArrowDown } from 'lucide-react'
import { StatsCard } from '@/components/dashboard/StatsCard'
import { UsageChart } from '@/components/dashboard/UsageChart'
import { TokenDonutChart } from '@/components/dashboard/TokenDonutChart'
import { SessionsChart } from '@/components/dashboard/SessionsChart'
import { TypeUsagePanel } from '@/components/dashboard/TypeUsagePanel'
import { useApi } from '@/hooks/useApi'
import { cn } from '@/lib/utils'
import type { DashboardStats, InstanceType, InstanceUsage, TypeUsage } from '@/types'

/** 类型筛选选项：空字符串代表「全部」 */
type TypeFilter = '' | InstanceType

const TYPE_FILTERS: { value: TypeFilter; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'voice', label: '语音' },
  { value: 'chat', label: '对话' },
  { value: 'image', label: '图像' },
]

export function DashboardPage() {
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('')

  // useApi 会在 url 变化时自动重新请求，因此从选中类型构造带筛选的 URL
  const typeQuery = typeFilter ? `?type=${typeFilter}` : ''
  const { data: stats, loading: statsLoading } = useApi<DashboardStats>(
    `/api/dashboard/stats${typeQuery}`
  )
  const { data: usage, loading: usageLoading } = useApi<InstanceUsage[]>(
    `/api/dashboard/usage-by-instance${typeQuery}`
  )
  // 跨类型分布不随类型筛选变化，始终展示 voice/chat/image 的完整拆分
  const { data: typeUsage } = useApi<TypeUsage[]>('/api/dashboard/usage-by-type')

  const loading = statsLoading || usageLoading
  const instanceUsage = usage ?? []
  const typeUsageData = typeUsage ?? []

  return (
    <div className="space-y-6">
      {/* Header + Type Filter */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <h1 className="bg-gradient-to-r from-indigo-600 to-violet-500 bg-clip-text text-3xl font-bold tracking-tight text-transparent">
            Dashboard
          </h1>
          <p className="text-sm text-muted-foreground">跨语音 / 对话 / 图像的用量与统计概览</p>
        </div>
        <div
          role="tablist"
          aria-label="按测试类型筛选"
          className="inline-flex items-center gap-1 self-start rounded-xl bg-muted/60 p-1 ring-1 ring-border"
        >
          {TYPE_FILTERS.map((option) => {
            const active = typeFilter === option.value
            return (
              <button
                key={option.value || 'all'}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setTypeFilter(option.value)}
                className={cn(
                  'rounded-lg px-3.5 py-1.5 text-sm font-medium transition',
                  active
                    ? 'bg-gradient-to-r from-indigo-600 to-violet-500 text-white shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {option.label}
              </button>
            )
          })}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center p-12">
          <p className="text-muted-foreground">加载中...</p>
        </div>
      ) : (
        <>
          {/* Row 1: Stats Cards */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            <StatsCard icon={Server} label="总实例数" value={stats?.total_instances ?? 0} color="indigo" />
            <StatsCard icon={FlaskConical} label="总测试数" value={stats?.total_tests ?? 0} color="violet" />
            <StatsCard icon={MessageSquare} label="总会话数" value={stats?.total_sessions ?? 0} color="sky" />
            <StatsCard icon={Zap} label="活跃会话" value={stats?.active_sessions ?? 0} color="emerald" />
            <StatsCard icon={ArrowUp} label="总输入 Tokens" value={stats?.total_input_tokens ?? 0} color="violet" />
            <StatsCard icon={ArrowDown} label="总输出 Tokens" value={stats?.total_output_tokens ?? 0} color="amber" />
          </div>

          {/* Row 2: Per-type usage breakdown */}
          <TypeUsagePanel data={typeUsageData} />

          {/* Row 3: Usage Chart + Token Donut */}
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <UsageChart data={instanceUsage} />
            </div>
            <div className="lg:col-span-1">
              <TokenDonutChart
                inputTokens={stats?.total_input_tokens ?? 0}
                outputTokens={stats?.total_output_tokens ?? 0}
              />
            </div>
          </div>

          {/* Row 4: Sessions Chart */}
          <SessionsChart data={instanceUsage} />
        </>
      )}
    </div>
  )
}
