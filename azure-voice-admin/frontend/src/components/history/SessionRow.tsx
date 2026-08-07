import { useNavigate } from 'react-router-dom'
import { Trash2, Coins } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { Session } from '@/types'

interface SessionRowProps {
  session: Session
  onDelete: (id: string) => void
}

interface StatusStyle {
  label: string
  pill: string
  dot: string
}

const statusConfig: Record<Session['status'], StatusStyle> = {
  connecting: {
    label: '连接中',
    pill: 'bg-amber-100 text-amber-700 ring-1 ring-amber-200',
    dot: 'bg-amber-500',
  },
  connected: {
    label: '已连接',
    pill: 'bg-sky-100 text-sky-700 ring-1 ring-sky-200',
    dot: 'bg-sky-500',
  },
  completed: {
    label: '已完成',
    pill: 'bg-emerald-100 text-emerald-700 ring-1 ring-emerald-200',
    dot: 'bg-emerald-500',
  },
  error: {
    label: '错误',
    pill: 'bg-rose-100 text-rose-700 ring-1 ring-rose-200',
    dot: 'bg-rose-500',
  },
  cancelled: {
    label: '已取消',
    pill: 'bg-slate-100 text-slate-600 ring-1 ring-slate-200',
    dot: 'bg-slate-400',
  },
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
      className="cursor-pointer transition-colors hover:bg-muted/40"
      onClick={() => navigate(`/history/${session.id}`)}
    >
      <td className="px-4 py-3 text-sm font-medium">{session.instance_name}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground">
        {formatTime(session.start_time)}
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground">
        {formatDuration(session.start_time, session.end_time)}
      </td>
      <td className="px-4 py-3 text-sm">
        <div className="flex items-center gap-1.5">
          <Coins className="h-3.5 w-3.5 text-amber-500" aria-hidden="true" />
          <span className="font-medium">{totalTokens.toLocaleString()}</span>
          <span className="text-xs text-muted-foreground">
            ({session.input_tokens.toLocaleString()} / {session.output_tokens.toLocaleString()})
          </span>
        </div>
      </td>
      <td className="px-4 py-3">
        <span
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold',
            status.pill
          )}
        >
          <span className={cn('h-1.5 w-1.5 rounded-full', status.dot)} aria-hidden="true" />
          {status.label}
        </span>
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
          <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" aria-hidden="true" />
        </Button>
      </td>
    </tr>
  )
}
