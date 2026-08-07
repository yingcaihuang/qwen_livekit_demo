import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { InstanceUsage } from '@/types'

interface UsageChartProps {
  data: InstanceUsage[]
}

export function UsageChart({ data }: UsageChartProps) {
  if (data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>实例 Token 用量</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">暂无数据</p>
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
        <ResponsiveContainer width="100%" height={Math.max(data.length * 60, 200)}>
          <BarChart data={data} layout="vertical" margin={{ top: 5, right: 30, left: 80, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" />
            <YAxis type="category" dataKey="instance_name" width={70} />
            <Tooltip formatter={(value: number) => value.toLocaleString()} />
            <Legend />
            <Bar dataKey="total_input_tokens" name="输入 Tokens" fill="#6366f1" stackId="tokens" />
            <Bar dataKey="total_output_tokens" name="输出 Tokens" fill="#f59e0b" stackId="tokens" />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
