import type { LucideIcon } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

export type StatsCardColor = 'indigo' | 'emerald' | 'amber' | 'sky' | 'violet'

interface StatsCardProps {
  icon: LucideIcon
  label: string
  value: number | string
  color?: StatsCardColor
}

interface ColorScheme {
  gradient: string
  ring: string
  accent: string
  chip: string
  value: string
}

const COLOR_SCHEMES: Record<StatsCardColor, ColorScheme> = {
  indigo: {
    gradient: 'bg-gradient-to-br from-indigo-500/10 to-violet-500/5',
    ring: 'ring-1 ring-indigo-500/20',
    accent: 'before:bg-indigo-500',
    chip: 'bg-indigo-500/15 text-indigo-600',
    value: 'text-indigo-950',
  },
  sky: {
    gradient: 'bg-gradient-to-br from-sky-500/10 to-cyan-500/5',
    ring: 'ring-1 ring-sky-500/20',
    accent: 'before:bg-sky-500',
    chip: 'bg-sky-500/15 text-sky-600',
    value: 'text-sky-950',
  },
  emerald: {
    gradient: 'bg-gradient-to-br from-emerald-500/10 to-teal-500/5',
    ring: 'ring-1 ring-emerald-500/20',
    accent: 'before:bg-emerald-500',
    chip: 'bg-emerald-500/15 text-emerald-600',
    value: 'text-emerald-950',
  },
  violet: {
    gradient: 'bg-gradient-to-br from-violet-500/10 to-purple-500/5',
    ring: 'ring-1 ring-violet-500/20',
    accent: 'before:bg-violet-500',
    chip: 'bg-violet-500/15 text-violet-600',
    value: 'text-violet-950',
  },
  amber: {
    gradient: 'bg-gradient-to-br from-amber-500/10 to-orange-500/5',
    ring: 'ring-1 ring-amber-500/20',
    accent: 'before:bg-amber-500',
    chip: 'bg-amber-500/15 text-amber-600',
    value: 'text-amber-950',
  },
}

export function StatsCard({ icon: Icon, label, value, color = 'indigo' }: StatsCardProps) {
  const scheme = COLOR_SCHEMES[color]

  return (
    <Card
      className={cn(
        'relative overflow-hidden border-0 transition duration-200 hover:shadow-md hover:-translate-y-0.5',
        'before:absolute before:inset-y-0 before:left-0 before:w-1 before:content-[""]',
        scheme.gradient,
        scheme.ring,
        scheme.accent
      )}
    >
      <CardContent className="flex items-center gap-4 p-5">
        <div
          className={cn(
            'flex h-12 w-12 shrink-0 items-center justify-center rounded-xl',
            scheme.chip
          )}
        >
          <Icon className="h-6 w-6" aria-hidden="true" />
        </div>
        <div className="min-w-0 space-y-1">
          <p className="truncate text-sm font-medium text-muted-foreground">{label}</p>
          <p className={cn('text-2xl font-bold tracking-tight', scheme.value)}>
            {typeof value === 'number' ? value.toLocaleString() : value}
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
