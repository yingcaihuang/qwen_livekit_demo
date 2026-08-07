import { Cpu, Waypoints } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatEndpoint } from '@/lib/format'

interface MessageMetaProps {
  /** 生成该回复所用的模型 */
  model?: string | null
  /** 生成该回复所调用的完整 Azure 端点 URL */
  endpoint?: string | null
  className?: string
}

/**
 * assistant 回复的元信息页脚：展示一对高对比、带边框的实心药丸标签——
 * - 模型标签（Cpu 图标 + 模型名，emerald 绿色系）
 * - 端点标签（Waypoints 图标 + 简短端点，indigo 靛色系；title 为完整 URL）
 *
 * 无 model 且无 endpoint 时不渲染任何内容。两个标签采用彼此明显区分的
 * 配色，确保在白色消息卡片上清晰可读。
 */
export function MessageMeta({ model, endpoint, className }: MessageMetaProps) {
  const hasModel = Boolean(model)
  const hasEndpoint = Boolean(endpoint)
  if (!hasModel && !hasEndpoint) return null

  const shortEndpoint = formatEndpoint(endpoint)

  return (
    <div className={cn('mt-1.5 flex flex-wrap items-center gap-1.5', className)}>
      {hasModel && (
        <span
          className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-100 px-2 py-0.5 font-mono text-xs font-medium text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-300"
          title={model ?? undefined}
        >
          <Cpu className="h-3 w-3" aria-hidden="true" />
          {model}
        </span>
      )}
      {hasEndpoint && shortEndpoint && (
        <span
          className="inline-flex items-center gap-1 rounded-full border border-indigo-200 bg-indigo-100 px-2 py-0.5 font-mono text-xs font-medium text-indigo-700 dark:border-indigo-500/30 dark:bg-indigo-500/15 dark:text-indigo-300"
          title={endpoint ?? undefined}
        >
          <Waypoints className="h-3 w-3" aria-hidden="true" />
          {shortEndpoint}
        </span>
      )}
    </div>
  )
}
