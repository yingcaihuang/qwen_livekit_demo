import { Mic, MessageSquare, Image } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { InstanceType } from '@/types'

interface TypeBadgeConfig {
  label: string
  gradient: string
  icon: LucideIcon
}

const TYPE_CONFIG: Record<InstanceType, TypeBadgeConfig> = {
  voice: {
    label: '语音',
    gradient: 'from-indigo-500 to-violet-500',
    icon: Mic,
  },
  chat: {
    label: '对话',
    gradient: 'from-emerald-500 to-teal-500',
    icon: MessageSquare,
  },
  image: {
    label: '图像',
    gradient: 'from-amber-500 to-orange-500',
    icon: Image,
  },
}

/** 返回实例类型对应的中文标签（语音 / 对话 / 图像）。 */
export function getTypeLabel(type: InstanceType): string {
  return TYPE_CONFIG[type]?.label ?? type
}

interface TypeBadgeProps {
  type: InstanceType
  className?: string
}

/**
 * 类型徽章：以三色渐变胶囊 + 图标展示实例的测试类型。
 * voice → 靛紫 / chat → 翠绿 / image → 琥珀。
 */
export function TypeBadge({ type, className }: TypeBadgeProps) {
  const config = TYPE_CONFIG[type] ?? TYPE_CONFIG.voice
  const Icon = config.icon

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full bg-gradient-to-r px-2.5 py-0.5 text-xs font-semibold text-white shadow-sm',
        config.gradient,
        className
      )}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {config.label}
    </span>
  )
}
