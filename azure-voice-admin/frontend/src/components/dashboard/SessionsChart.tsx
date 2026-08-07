import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  type TooltipProps,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { InstanceUsage } from '@/types'

interface SessionsChartProps {
  data: InstanceUsage[]
}

function SessionsTooltip({ active, payload, label }: TooltipProps<number, string>) {
  const entry = payload?.[0]
  if (!active || !entry) {
    return null
  }
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-sm shadow-lg">
      <p className="mb-1 font-medium text-popover-foreground">{label}</p>
      <div className="flex items-center gap-2">
        <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" />
        <span className="text-muted-foreground">会话数</span>
        <span className="ml-auto font-medium text-popover-foreground">
          {(entry.value ?? 0).toLocaleString()}
        </span>
      </div>
    </div>
  )
}

export function SessionsChart({ data }: SessionsChartProps) {
  if (data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>各实例会话数</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-48 items-center justify-center">
            <p className="text-sm text-muted-foreground">暂无数据</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>各实例会话数</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <defs>
              <linearGradient id="sessionsGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#10b981" />
                <stop offset="100%" stopColor="#14b8a6" />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#e5e5e5" />
            <XAxis
              dataKey="instance_name"
              tick={{ fontSize: 12, fill: '#525252' }}
              tickLine={false}
              axisLine={{ stroke: '#e5e5e5' }}
            />
            <YAxis
              allowDecimals={false}
              tick={{ fontSize: 11, fill: '#737373' }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              content={<SessionsTooltip />}
              cursor={{ fill: 'rgba(16, 185, 129, 0.08)' }}
            />
            <Bar
              dataKey="session_count"
              name="会话数"
              fill="url(#sessionsGradient)"
              radius={[6, 6, 0, 0]}
              maxBarSize={64}
            />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
