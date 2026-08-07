import { useNavigate } from 'react-router-dom'
import { Play, Pencil, Trash2 } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
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

interface InstanceCardProps {
  instance: Instance
  onDelete: (id: string) => void
}

export function InstanceCard({ instance, onDelete }: InstanceCardProps) {
  const navigate = useNavigate()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{instance.name}</CardTitle>
        <CardDescription>{instance.description || '无描述'}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Endpoint</span>
          <span className="truncate max-w-[200px] font-mono text-xs" title={instance.endpoint}>
            {instance.endpoint}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Deployment</span>
          <span className="font-mono text-xs">{instance.deployment}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">创建时间</span>
          <span>{formatRelativeTime(instance.created_at)}</span>
        </div>
      </CardContent>
      <CardFooter className="gap-2">
        <Button
          size="sm"
          onClick={() => navigate(`/sessions/new?instance=${instance.id}`)}
        >
          <Play />
          Start Session
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => navigate(`/instances/${instance.id}`)}
        >
          <Pencil />
        </Button>
        <Button
          size="sm"
          variant="destructive"
          onClick={() => onDelete(instance.id)}
        >
          <Trash2 />
        </Button>
      </CardFooter>
    </Card>
  )
}
