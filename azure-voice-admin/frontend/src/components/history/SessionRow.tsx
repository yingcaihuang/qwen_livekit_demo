import { useNavigate } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { Session } from '@/types'

interface SessionRowProps {
  session: Session
  onDelete: (id: string) => void
}

const statusConfig: Record<Session['status'], { label: string; className: string }> = {
  connecting: { label: '连接中', className: 'bg-yellow-100 text-yellow-800 border-yellow-200' },
  connected: { label: '已连接', className: 'bg-blue-100 text-blue-800 border-blue-200' },
  completed: { label: '已完成', className: 'bg-green-100 text-green-800 border-green-200' },
  error: { label: '错误', className: 'bg-red-100 text-red-800 border-red-200' },
  cancelled: { label: '已取消', className: 'bg-gray-100 text-gray-800 border-gray-200' },
}

function formatDuration(startTime: string, endTime: string | null): string {
  if (!endTime) return '进行中'
  const start = new Date(startTime).getTime()
  const end = new Date(endTime).getTime()
  const diffMs = end - start
  if (diffMs < 0) return '—'
  const seconds = Math.floor(diffMs / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  if (hours > 0) {
    return `${hours}h ${minutes % 60}m ${seconds % 60}s`
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`
  }
  return `${seconds}s`
}

function formatTime(isoString: string): string {
  const date = new Date(isoString)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function SessionRow({ session, onDelete }: SessionRowProps) {
  const navigate = useNavigate()
  const status = statusConfig[session.status]
  const totalTokens = session.input_tokens + session.output_tokens

  return (
    <tr
      className="border-b hover:bg-muted/50 cursor-pointer transition-colors"
      onClick={() => navigate(`/history/${session.id}`)}
    >
      <td className="px-4 py-3 text-sm font-medium">{session.instance_name}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground">
        {formatTime(session.start_time)}
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground">
        {formatDuration(session.start_time, session.end_time)}
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground">
        {totalTokens.toLocaleString()}
      </td>
      <td className="px-4 py-3">
        <Badge className={status.className}>{status.label}</Badge>
      </td>
      <td className="px-4 py-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={(e) => {
            e.stopPropagation()
            onDelete(session.id)
          }}
          aria-label="删除会话"
        >
          <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
        </Button>
      </td>
    </tr>
  )
}
