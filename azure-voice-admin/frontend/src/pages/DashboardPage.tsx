import { Server, MessageSquare, Zap, ArrowUp, ArrowDown } from 'lucide-react'
import { StatsCard } from '@/components/dashboard/StatsCard'
import { UsageChart } from '@/components/dashboard/UsageChart'
import { TokenDonutChart } from '@/components/dashboard/TokenDonutChart'
import { SessionsChart } from '@/components/dashboard/SessionsChart'
import { useApi } from '@/hooks/useApi'
import type { DashboardStats, InstanceUsage } from '@/types'

export function DashboardPage() {
  const { data: stats, loading: statsLoading } = useApi<DashboardStats>('/api/dashboard/stats')
  const { data: usage, loading: usageLoading } = useApi<InstanceUsage[]>('/api/dashboard/usage-by-instance')

  if (statsLoading || usageLoading) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-muted-foreground">加载中...</p>
      </div>
    )
  }

  const instanceUsage = usage ?? []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-1">
        <h1 className="bg-gradient-to-r from-indigo-600 to-violet-500 bg-clip-text text-3xl font-bold tracking-tight text-transparent">
          Dashboard
        </h1>
        <p className="text-sm text-muted-foreground">实时用量与会话概览</p>
      </div>

      {/* Row 1: Stats Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatsCard icon={Server} label="总实例数" value={stats?.total_instances ?? 0} color="indigo" />
        <StatsCard icon={MessageSquare} label="总会话数" value={stats?.total_sessions ?? 0} color="sky" />
        <StatsCard icon={Zap} label="活跃会话" value={stats?.active_sessions ?? 0} color="emerald" />
        <StatsCard icon={ArrowUp} label="总输入 Tokens" value={stats?.total_input_tokens ?? 0} color="violet" />
        <StatsCard icon={ArrowDown} label="总输出 Tokens" value={stats?.total_output_tokens ?? 0} color="amber" />
      </div>

      {/* Row 2: Usage Chart + Token Donut */}
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

      {/* Row 3: Sessions Chart */}
      <SessionsChart data={instanceUsage} />
    </div>
  )
}
