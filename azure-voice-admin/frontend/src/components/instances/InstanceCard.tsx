import { useNavigate } from 'react-router-dom'
import { Play, Pencil, Trash2, Link, Boxes, Clock } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { TypeBadge } from './TypeBadge'
import { cn } from '@/lib/utils'
import type { Instance } from '@/types'

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffDay > 0) return `${diffDay} 天前`
  if (diffHour > 0) return `${diffHour} 小时前`
  if (diffMin > 0) return `${diffMin} 分钟前`
  return '刚刚'
}

const AVATAR_GRADIENTS: readonly string[] = [
  'from-indigo-500 to-violet-500',
  'from-emerald-500 to-teal-500',
  'from-amber-500 to-orange-500',
  'from-sky-500 to-cyan-500',
  'from-rose-500 to-pink-500',
  'from-fuchsia-500 to-purple-500',
] as const

const FALLBACK_GRADIENT = 'from-slate-500 to-gray-500'

function pickGradient(key: string): string {
  let hash = 0
  for (let i = 0; i < key.length; i++) {
    hash = (hash * 31 + key.charCodeAt(i)) | 0
  }
  const index = Math.abs(hash) % AVATAR_GRADIENTS.length
  return AVATAR_GRADIENTS[index] ?? FALLBACK_GRADIENT
}

function getInitial(name: string): string {
  const trimmed = name.trim()
  return trimmed.length > 0 ? trimmed.charAt(0).toUpperCase() : '?'
}

interface InstanceCardProps {
  instance: Instance
  onDelete: (id: string) => void
}

const START_ROUTE_BY_TYPE: Record<Instance['type'], string> = {
  voice: '/sessions/new',
  chat: '/chat/new',
  image: '/images/new',
  translate: '/translate/new',
  transcribe: '/transcribe/new',
}

const START_LABEL_BY_TYPE: Record<Instance['type'], string> = {
  voice: 'Start Session',
  chat: '开始对话',
  image: '生成图像',
  translate: '开始翻译',
  transcribe: '开始转录',
}

export function InstanceCard({ instance, onDelete }: InstanceCardProps) {
  const navigate = useNavigate()
  const gradient = pickGradient(instance.id || instance.name)
  const startRoute = START_ROUTE_BY_TYPE[instance.type] ?? '/sessions/new'
  const startLabel = START_LABEL_BY_TYPE[instance.type] ?? 'Start Session'

  return (
    <Card className="relative overflow-hidden transition duration-200 hover:shadow-md hover:-translate-y-0.5">
      {/* Top gradient accent bar */}
      <div className={cn('absolute inset-x-0 top-0 h-1 bg-gradient-to-r', gradient)} aria-hidden="true" />
      <CardHeader className="flex-row items-start gap-3 space-y-0 pt-6">
        <div
          className={cn(
            'flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-lg font-bold text-white shadow-sm',
            gradient
          )}
          aria-hidden="true"
        >
          {getInitial(instance.name)}
        </div>
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-2">
            <CardTitle className="truncate text-lg" title={instance.name}>
              {instance.name}
            </CardTitle>
            <TypeBadge type={instance.type} className="shrink-0" />
          </div>
          <CardDescription className="truncate">{instance.description || '无描述'}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-2.5 text-sm">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <Link className="h-3.5 w-3.5" aria-hidden="true" />
            Endpoint
          </span>
          <span className="max-w-[200px] truncate font-mono text-xs" title={instance.endpoint}>
            {instance.endpoint}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <Boxes className="h-3.5 w-3.5" aria-hidden="true" />
            Deployment
          </span>
          <span className="font-mono text-xs">{instance.deployment}</span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <Clock className="h-3.5 w-3.5" aria-hidden="true" />
            创建时间
          </span>
          <span>{formatRelativeTime(instance.created_at)}</span>
        </div>
      </CardContent>
      <CardFooter className="gap-2">
        <Button
          size="sm"
          onClick={() => navigate(`${startRoute}?instance=${instance.id}`)}
          className="bg-gradient-to-r from-emerald-500 to-teal-500 text-white shadow-sm transition hover:opacity-90"
        >
          <Play aria-hidden="true" />
          {startLabel}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => navigate(`/instances/${instance.id}`)}
          aria-label="编辑实例"
        >
          <Pencil aria-hidden="true" />
        </Button>
        <Button
          size="sm"
          variant="destructive"
          onClick={() => onDelete(instance.id)}
          aria-label="删除实例"
        >
          <Trash2 aria-hidden="true" />
        </Button>
      </CardFooter>
    </Card>
  )
}
