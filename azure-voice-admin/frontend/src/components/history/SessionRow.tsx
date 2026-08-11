import { useNavigate } from 'react-router-dom'
import { Trash2, Coins } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { TypeBadge } from '@/components/instances/TypeBadge'
import { cn } from '@/lib/utils'
import type { HistoryItem } from '@/types'

interface HistoryRowProps {
  item: HistoryItem
  onDelete: (item: HistoryItem) => void
  selected?: boolean
  onToggleSelect?: () => void
}

interface StatusStyle {
  label: string
  pill: string
  dot: string
}

/** 状态样式表：涵盖 voice/chat 会话与 image 生成的常见状态值，未知状态回退到中性灰。 */
const statusConfig: Record<string, StatusStyle> = {
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
  active: {
    label: '进行中',
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
  // 图像生成异步任务状态
  pending: {
    label: '排队中',
    pill: 'bg-amber-100 text-amber-700 ring-1 ring-amber-200',
    dot: 'bg-amber-500',
  },
  processing: {
    label: '生成中',
    pill: 'bg-sky-100 text-sky-700 ring-1 ring-sky-200',
    dot: 'bg-sky-500',
  },
  failed: {
    label: '失败',
    pill: 'bg-rose-100 text-rose-700 ring-1 ring-rose-200',
    dot: 'bg-rose-500',
  },
}

function getStatusStyle(status: string): StatusStyle {
  return (
    statusConfig[status] ?? {
      label: status || '未知',
      pill: 'bg-slate-100 text-slate-600 ring-1 ring-slate-200',
      dot: 'bg-slate-400',
    }
  )
}

function formatTime(isoString: string): string {
  const date = new Date(isoString)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/**
 * 根据历史条目类型解析目标路由：
 * - image → 只读图像详情
 * - chat  → 可续聊的对话测试页（复用 session_id，加载历史消息后继续对话）
 * - voice → 只读会话详情
 */
function detailPath(item: HistoryItem): string {
  switch (item.type) {
    case 'image':
      return `/history/image/${item.id}`
    case 'chat':
      return `/chat/new?instance=${item.instance_id}&session=${item.id}`
    default:
      return `/history/${item.id}`
  }
}

export function SessionRow({ item, onDelete, selected, onToggleSelect }: HistoryRowProps) {
  const navigate = useNavigate()
  const status = getStatusStyle(item.status)
  const totalTokens = item.input_tokens + item.output_tokens

  return (
    <tr
      className="cursor-pointer transition-colors hover:bg-muted/40"
      onClick={() => navigate(detailPath(item))}
    >
      <td className="px-4 py-3">
        {onToggleSelect && (
          <input
            type="checkbox"
            checked={selected}
            onChange={(e) => { e.stopPropagation(); onToggleSelect() }}
            onClick={(e) => e.stopPropagation()}
            className="h-4 w-4 rounded border-gray-300"
            aria-label={`选择 ${item.title || item.id}`}
          />
        )}
      </td>
      <td className="px-4 py-3">
        <TypeBadge type={item.type} />
      </td>
      <td className="max-w-[22rem] px-4 py-3 text-sm font-medium">
        <span className="block truncate" title={item.title}>
          {item.title || '—'}
        </span>
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground">{item.instance_name}</td>
      <td className="px-4 py-3 text-sm text-muted-foreground">{formatTime(item.start_time)}</td>
      <td className="px-4 py-3 text-sm">
        <div className="flex items-center gap-1.5">
          <Coins className="h-3.5 w-3.5 text-amber-500" aria-hidden="true" />
          <span className="font-medium">{totalTokens.toLocaleString()}</span>
          <span className="text-xs text-muted-foreground">
            ({item.input_tokens.toLocaleString()} / {item.output_tokens.toLocaleString()})
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
            onDelete(item)
          }}
          aria-label="删除记录"
        >
          <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" aria-hidden="true" />
        </Button>
      </td>
    </tr>
  )
}
