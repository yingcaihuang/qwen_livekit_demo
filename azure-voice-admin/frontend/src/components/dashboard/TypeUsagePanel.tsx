import { Mic, MessageSquare, Image as ImageIcon, Languages, FileText, type LucideIcon } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { InstanceType, TypeUsage } from '@/types'

interface TypeUsagePanelProps {
  data: TypeUsage[]
}

interface TypeMeta {
  label: string
  icon: LucideIcon
  gradient: string
  ring: string
  chip: string
  accent: string
}

const TYPE_META: Record<InstanceType, TypeMeta> = {
  voice: {
    label: '语音',
    icon: Mic,
    gradient: 'bg-gradient-to-br from-indigo-500/10 to-violet-500/5',
    ring: 'ring-1 ring-indigo-500/20',
    chip: 'bg-indigo-500/15 text-indigo-600',
    accent: 'before:bg-indigo-500',
  },
  chat: {
    label: '对话',
    icon: MessageSquare,
    gradient: 'bg-gradient-to-br from-sky-500/10 to-cyan-500/5',
    ring: 'ring-1 ring-sky-500/20',
    chip: 'bg-sky-500/15 text-sky-600',
    accent: 'before:bg-sky-500',
  },
  image: {
    label: '图像',
    icon: ImageIcon,
    gradient: 'bg-gradient-to-br from-emerald-500/10 to-teal-500/5',
    ring: 'ring-1 ring-emerald-500/20',
    chip: 'bg-emerald-500/15 text-emerald-600',
    accent: 'before:bg-emerald-500',
  },
  translate: {
    label: '翻译',
    icon: Languages,
    gradient: 'bg-gradient-to-br from-cyan-500/10 to-blue-500/5',
    ring: 'ring-1 ring-cyan-500/20',
    chip: 'bg-cyan-500/15 text-cyan-600',
    accent: 'before:bg-cyan-500',
  },
  transcribe: {
    label: '转录',
    icon: FileText,
    gradient: 'bg-gradient-to-br from-rose-500/10 to-pink-500/5',
    ring: 'ring-1 ring-rose-500/20',
    chip: 'bg-rose-500/15 text-rose-600',
    accent: 'before:bg-rose-500',
  },
}

const TYPE_ORDER: InstanceType[] = ['voice', 'chat', 'image']

/**
 * 按测试类型（voice / chat / image）展示聚合用量的彩色卡片面板。
 * 无论后端是否返回某类型，都渲染三张卡片，缺失类型以零值展示（空态友好）。
 */
export function TypeUsagePanel({ data }: TypeUsagePanelProps) {
  const byType = new Map<InstanceType, TypeUsage>()
  for (const item of data) {
    byType.set(item.type, item)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>按类型用量</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-3">
          {TYPE_ORDER.map((type) => {
            const meta = TYPE_META[type]
            const usage = byType.get(type)
            const Icon = meta.icon
            return (
              <div
                key={type}
                className={cn(
                  'relative overflow-hidden rounded-xl p-4',
                  'before:absolute before:inset-y-0 before:left-0 before:w-1 before:content-[""]',
                  meta.gradient,
                  meta.ring,
                  meta.accent
                )}
              >
                <div className="flex items-center gap-3">
                  <div
                    className={cn(
                      'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
                      meta.chip
                    )}
                  >
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground">{meta.label}</p>
                    <p className="text-xs text-muted-foreground">
                      {(usage?.test_count ?? 0).toLocaleString()} 次测试
                    </p>
                  </div>
                </div>
                <dl className="mt-4 space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <dt className="text-muted-foreground">输入 Tokens</dt>
                    <dd className="font-semibold text-foreground">
                      {(usage?.total_input_tokens ?? 0).toLocaleString()}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <dt className="text-muted-foreground">输出 Tokens</dt>
                    <dd className="font-semibold text-foreground">
                      {(usage?.total_output_tokens ?? 0).toLocaleString()}
                    </dd>
                  </div>
                </dl>
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
