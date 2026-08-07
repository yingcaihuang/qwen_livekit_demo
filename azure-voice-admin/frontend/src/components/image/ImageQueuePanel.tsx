import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as Dialog from '@radix-ui/react-dialog'
import { Clock, Layers, Loader2, Sparkles, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ImageQueue, ImageQueueItem } from '@/types'

interface ImageQueuePanelProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const POLL_INTERVAL_MS = 2000

/** 将 ISO 时间转换为「刚刚 / N 分钟前 / N 小时前」的相对描述。 */
function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const diffSec = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (diffSec < 60) return '刚刚'
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin} 分钟前`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour} 小时前`
  const diffDay = Math.floor(diffHour / 24)
  return `${diffDay} 天前`
}

interface StatusStyle {
  label: string
  pill: string
  dot: string
}

const STATUS_STYLE: Record<ImageQueueItem['status'], StatusStyle> = {
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
}

function StatusPill({ status }: { status: ImageQueueItem['status'] }) {
  const style = STATUS_STYLE[status]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold',
        style.pill,
      )}
    >
      {status === 'processing' ? (
        <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
      ) : (
        <span className={cn('h-1.5 w-1.5 rounded-full', style.dot)} aria-hidden="true" />
      )}
      {style.label}
    </span>
  )
}

/** 顶部统计小药丸。 */
function CountPill({
  label,
  count,
  className,
}: {
  label: string
  count: number
  className: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold',
        className,
      )}
    >
      {label}
      <span className="tabular-nums">{count}</span>
    </span>
  )
}

export function ImageQueuePanel({ open, onOpenChange }: ImageQueuePanelProps) {
  const navigate = useNavigate()
  const [queue, setQueue] = useState<ImageQueue | null>(null)
  const [loading, setLoading] = useState(false)

  // 打开时立即拉取一次并每 2s 轮询；关闭/卸载时停止。
  useEffect(() => {
    if (!open) return

    let cancelled = false

    const fetchQueue = async () => {
      try {
        const res = await fetch('/api/images/queue')
        if (!res.ok) return
        const data = (await res.json()) as ImageQueue
        if (!cancelled) setQueue(data)
      } catch {
        // 轮询失败保持静默，下个周期继续尝试
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    setLoading(true)
    void fetchQueue()
    const timer = setInterval(fetchQueue, POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [open])

  const handleItemClick = useCallback(
    (item: ImageQueueItem) => {
      onOpenChange(false)
      navigate(`/history/image/${item.id}`)
    },
    [navigate, onOpenChange],
  )

  const items = queue?.items ?? []
  const total = queue?.total ?? 0

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm transition-opacity duration-300 data-[state=closed]:opacity-0 data-[state=open]:opacity-100" />
        <Dialog.Content
          className={cn(
            'fixed inset-y-0 right-0 z-50 flex h-full w-full max-w-md flex-col bg-background shadow-2xl outline-none',
            'transition-transform duration-300 ease-out',
            'data-[state=open]:translate-x-0 data-[state=closed]:translate-x-full',
            'motion-reduce:transition-none',
          )}
        >
          {/* Header */}
          <div className="relative overflow-hidden border-b bg-gradient-to-br from-amber-500 via-orange-500 to-rose-500 px-6 py-5 text-white">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/20 backdrop-blur">
                  <Sparkles className="h-5 w-5" aria-hidden="true" />
                </div>
                <div>
                  <Dialog.Title className="text-lg font-bold leading-tight">生成队列</Dialog.Title>
                  <Dialog.Description className="text-xs text-white/80">
                    共 {total} 个进行中的任务
                  </Dialog.Description>
                </div>
              </div>
              <Dialog.Close
                className="rounded-lg p-1.5 text-white/90 transition-colors hover:bg-white/20"
                aria-label="关闭队列"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </Dialog.Close>
            </div>

            {/* 统计药丸 */}
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <CountPill label="排队中" count={queue?.pending ?? 0} className="bg-white/20 text-white" />
              <CountPill label="生成中" count={queue?.processing ?? 0} className="bg-white/20 text-white" />
            </div>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto px-4 py-4">
            {items.length === 0 ? (
              <div className="flex min-h-[60%] flex-col items-center justify-center gap-3 px-6 py-16 text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-100 to-orange-100 text-orange-500">
                  {loading ? (
                    <Loader2 className="h-7 w-7 animate-spin" aria-hidden="true" />
                  ) : (
                    <Layers className="h-7 w-7" aria-hidden="true" />
                  )}
                </div>
                <p className="text-sm font-medium text-muted-foreground">
                  {loading ? '正在加载队列…' : '队列空闲，暂无进行中的生成任务'}
                </p>
              </div>
            ) : (
              <ul className="space-y-3">
                {items.map((item, index) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => handleItemClick(item)}
                      className="group flex w-full items-start gap-3 rounded-2xl border border-border/60 bg-gradient-to-br from-white to-amber-50/40 p-3.5 text-left shadow-sm transition-all hover:border-amber-300 hover:shadow-md"
                    >
                      {/* 序号 */}
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-orange-500 text-xs font-bold text-white shadow-sm">
                        {index + 1}
                      </span>

                      <div className="min-w-0 flex-1 space-y-1.5">
                        <div className="flex items-center justify-between gap-2">
                          <StatusPill status={item.status} />
                          <span className="flex items-center gap-1 text-xs text-muted-foreground">
                            <Clock className="h-3 w-3" aria-hidden="true" />
                            {relativeTime(item.created_at)}
                          </span>
                        </div>

                        <p
                          className="truncate text-sm font-medium text-foreground"
                          title={item.prompt}
                        >
                          {item.prompt || '（无提示词）'}
                        </p>

                        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted-foreground">
                          <span className="truncate" title={item.instance_name}>
                            {item.instance_name}
                          </span>
                          <span className="text-border">·</span>
                          <span className="tabular-nums">{item.size}</span>
                          <span className="text-border">·</span>
                          <span className="tabular-nums">×{item.n}</span>
                        </div>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
