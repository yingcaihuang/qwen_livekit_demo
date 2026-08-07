import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
  type TooltipProps,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface TokenDonutChartProps {
  inputTokens: number
  outputTokens: number
}

const INPUT_COLOR = '#6366f1'
const OUTPUT_COLOR = '#f59e0b'

function DonutTooltip({ active, payload }: TooltipProps<number, string>) {
  const entry = payload?.[0]
  if (!active || !entry) {
    return null
  }
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-sm shadow-lg">
      <div className="flex items-center gap-2">
        <span
          className="inline-block h-2.5 w-2.5 rounded-full"
          style={{ backgroundColor: entry.payload?.fill }}
        />
        <span className="text-muted-foreground">{entry.name}</span>
        <span className="ml-auto font-medium text-popover-foreground">
          {(entry.value ?? 0).toLocaleString()}
        </span>
      </div>
    </div>
  )
}

export function TokenDonutChart({ inputTokens, outputTokens }: TokenDonutChartProps) {
  const total = inputTokens + outputTokens

  if (total === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Token 输入/输出占比</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-64 items-center justify-center">
            <p className="text-sm text-muted-foreground">暂无数据</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  const chartData = [
    { name: '输入 Tokens', value: inputTokens, fill: INPUT_COLOR },
    { name: '输出 Tokens', value: outputTokens, fill: OUTPUT_COLOR },
  ]

  const renderPercent = (percent?: number) =>
    percent === undefined ? '' : `${(percent * 100).toFixed(1)}%`

  return (
    <Card>
      <CardHeader>
        <CardTitle>Token 输入/输出占比</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="relative">
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <defs>
                <linearGradient id="donutInputGradient" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor="#818cf8" />
                  <stop offset="100%" stopColor="#6366f1" />
                </linearGradient>
                <linearGradient id="donutOutputGradient" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0%" stopColor="#fbbf24" />
                  <stop offset="100%" stopColor="#f59e0b" />
                </linearGradient>
              </defs>
              <Pie
                data={chartData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={70}
                outerRadius={100}
                paddingAngle={2}
                stroke="none"
                label={({ percent }) => renderPercent(percent)}
                labelLine={false}
              >
                <Cell fill="url(#donutInputGradient)" />
                <Cell fill="url(#donutOutputGradient)" />
              </Pie>
              <Tooltip content={<DonutTooltip />} />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="pointer-events-none absolute inset-x-0 top-[110px] flex -translate-y-1/2 flex-col items-center">
            <span className="text-xs text-muted-foreground">总计</span>
            <span className="text-2xl font-bold tracking-tight">{total.toLocaleString()}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
