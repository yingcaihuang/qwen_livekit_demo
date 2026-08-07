import { Calendar, CheckCircle2, Timer, Zap, type LucideIcon } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { formatDateTime, formatDuration } from '@/lib/format'

interface ImageMetricsProps {
  startedAt?: string | null
  endedAt?: string | null
  durationMs?: number | null
  ttfbMs?: number | null
}

type TileColor = 'sky' | 'emerald' | 'amber' | 'violet'

interface TileScheme {
  gradient: string
  ring: string
  chip: string
  accent: string
  value: string
}

const TILE_SCHEMES: Record<TileColor, TileScheme> = {
  sky: {
    gradient: 'bg-gradient-to-br from-sky-500/10 to-cyan-500/5',
    ring: 'ring-1 ring-sky-500/20',
    chip: 'bg-sky-500/15 text-sky-600',
    accent: 'before:bg-sky-500',
    value: 'text-sky-950',
  },
  emerald: {
    gradient: 'bg-gradient-to-br from-emerald-500/10 to-teal-500/5',
    ring: 'ring-1 ring-emerald-500/20',
    chip: 'bg-emerald-500/15 text-emerald-600',
    accent: 'before:bg-emerald-500',
    value: 'text-emerald-950',
  },
  amber: {
    gradient: 'bg-gradient-to-br from-amber-500/10 to-orange-500/5',
    ring: 'ring-1 ring-amber-500/20',
    chip: 'bg-amber-500/15 text-amber-600',
    accent: 'before:bg-amber-500',
    value: 'text-amber-950',
  },
  violet: {
    gradient: 'bg-gradient-to-br from-violet-500/10 to-purple-500/5',
    ring: 'ring-1 ring-violet-500/20',
    chip: 'bg-violet-500/15 text-violet-600',
    accent: 'before:bg-violet-500',
    value: 'text-violet-950',
  },
}

interface MetricTileProps {
  icon: LucideIcon
  label: string
  value: string
  color: TileColor
  emphasized?: boolean
}

function MetricTile({ icon: Icon, label, value, color, emphasized }: MetricTileProps) {
  const scheme = TILE_SCHEMES[color]
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-xl p-4',
        'before:absolute before:inset-y-0 before:left-0 before:w-1 before:content-[""]',
        scheme.gradient,
        scheme.ring,
        scheme.accent,
      )}
    >
      <div className="flex items-center gap-3">
        <div
          className={cn(
            'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
            scheme.chip,
          )}
        >
          <Icon className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-xs font-medium text-muted-foreground">{label}</p>
          <p
            className={cn(
              'truncate font-semibold tracking-tight',
              emphasized ? 'text-lg' : 'text-sm',
              scheme.value,
            )}
            title={value}
          >
            {value}
          </p>
        </div>
      </div>
    </div>
  )
}

/**
 * 图像生成性能指标面板：以彩色渐变瓦片展示开始/结束时间、总耗时与首字节耗时。
 * 若四项均缺失（旧记录），则不渲染任何内容。
 */
export function ImageMetrics({ startedAt, endedAt, durationMs, ttfbMs }: ImageMetricsProps) {
  const allEmpty =
    (startedAt === null || startedAt === undefined) &&
    (endedAt === null || endedAt === undefined) &&
    (durationMs === null || durationMs === undefined) &&
    (ttfbMs === null || ttfbMs === undefined)

  if (allEmpty) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
          <Timer className="h-4 w-4 text-sky-500" />
          性能指标
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricTile
            icon={Calendar}
            label="开始时间"
            value={formatDateTime(startedAt)}
            color="sky"
          />
          <MetricTile
            icon={CheckCircle2}
            label="结束时间"
            value={formatDateTime(endedAt)}
            color="emerald"
          />
          <MetricTile
            icon={Timer}
            label="总耗时"
            value={formatDuration(durationMs)}
            color="amber"
            emphasized
          />
          <MetricTile
            icon={Zap}
            label="首字节耗时 / TTFB"
            value={formatDuration(ttfbMs)}
            color="violet"
            emphasized
          />
        </div>
      </CardContent>
    </Card>
  )
}
