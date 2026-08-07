import type { LucideIcon } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'

interface StatsCardProps {
  icon: LucideIcon
  label: string
  value: number | string
}

export function StatsCard({ icon: Icon, label, value }: StatsCardProps) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="h-5 w-5" />
        </div>
        <div className="space-y-0.5">
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="text-2xl font-bold">{typeof value === 'number' ? value.toLocaleString() : value}</p>
        </div>
      </CardContent>
    </Card>
  )
}
