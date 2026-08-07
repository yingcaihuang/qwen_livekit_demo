import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  type TooltipProps,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { InstanceUsage } from '@/types'

interface UsageChartProps {
  data: InstanceUsage[]
}

function ChartTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) {
    return null
  }
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-sm shadow-lg">
      <p className="mb-1 font-medium text-popover-foreground">{label}</p>
      <div className="space-y-0.5">
        {payload.map((entry) => (
          <div key={entry.name} className="flex items-center gap-2">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            <span className="text-muted-foreground">{entry.name}</span>
            <span className="ml-auto font-medium text-popover-foreground">
              {(entry.value ?? 0).toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function UsageChart({ data }: UsageChartProps) {
  if (data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>实例 Token 用量</CardTitle>
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
        <CardTitle>实例 Token 用量</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={Math.max(data.length * 64, 240)}>
          <BarChart
            data={data}
            layout="vertical"
            barCategoryGap="20%"
            margin={{ top: 8, right: 24, left: 16, bottom: 8 }}
          >
            <defs>
              <linearGradient id="usageInputGradient" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="#6366f1" />
                <stop offset="100%" stopColor="#8b5cf6" />
              </linearGradient>
              <linearGradient id="usageOutputGradient" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="#f59e0b" />
                <stop offset="100%" stopColor="#f97316" />
              </linearGradient>
            </defs>
            <CartesianGrid
              horizontal={false}
              strokeDasharray="3 3"
              stroke="#e5e5e5"
            />
            <XAxis
              type="number"
              tick={{ fontSize: 11, fill: '#737373' }}
              tickLine={false}
              axisLine={{ stroke: '#e5e5e5' }}
              tickFormatter={(value: number) => value.toLocaleString()}
            />
            <YAxis
              type="category"
              dataKey="instance_name"
              width={90}
              tick={{ fontSize: 12, fill: '#525252' }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              content={<ChartTooltip />}
              cursor={{ fill: 'rgba(99, 102, 241, 0.06)' }}
            />
            <Legend
              iconType="circle"
              wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
            />
            <Bar
              dataKey="total_input_tokens"
              name="输入 Tokens"
              fill="url(#usageInputGradient)"
              stackId="tokens"
              radius={[4, 0, 0, 4]}
            />
            <Bar
              dataKey="total_output_tokens"
              name="输出 Tokens"
              fill="url(#usageOutputGradient)"
              stackId="tokens"
              radius={[0, 4, 4, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
