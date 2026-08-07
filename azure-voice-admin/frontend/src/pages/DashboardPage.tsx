import { Server, MessageSquare, Zap, ArrowUp, ArrowDown } from 'lucide-react'
import { StatsCard } from '@/components/dashboard/StatsCard'
import { UsageChart } from '@/components/dashboard/UsageChart'
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

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        <StatsCard icon={Server} label="总实例数" value={stats?.total_instances ?? 0} />
        <StatsCard icon={MessageSquare} label="总会话数" value={stats?.total_sessions ?? 0} />
        <StatsCard icon={Zap} label="活跃会话" value={stats?.active_sessions ?? 0} />
        <StatsCard icon={ArrowUp} label="总输入 Tokens" value={stats?.total_input_tokens ?? 0} />
        <StatsCard icon={ArrowDown} label="总输出 Tokens" value={stats?.total_output_tokens ?? 0} />
      </div>

      {/* Usage Chart */}
      <UsageChart data={usage ?? []} />
    </div>
  )
}
