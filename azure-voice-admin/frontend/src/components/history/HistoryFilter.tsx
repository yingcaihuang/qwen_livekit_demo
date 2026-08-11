import { Mic, MessageSquare, Image, Languages, FileText } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Instance, InstanceType } from '@/types'

/** 类型筛选值：空串表示「全部」。 */
export type HistoryTypeFilter = '' | InstanceType

interface HistoryFilterProps {
  typeFilter: HistoryTypeFilter
  instanceFilter: string
  instances: Instance[]
  onTypeChange: (value: HistoryTypeFilter) => void
  onInstanceChange: (value: string) => void
}

const TYPE_OPTIONS: { value: HistoryTypeFilter; label: string; icon: React.ComponentType<{ className?: string }>; color: string }[] = [
  { value: '', label: '全部', icon: () => null, color: 'from-gray-500 to-gray-600' },
  { value: 'voice', label: '语音', icon: Mic, color: 'from-indigo-500 to-violet-500' },
  { value: 'chat', label: '对话', icon: MessageSquare, color: 'from-emerald-500 to-teal-500' },
  { value: 'image', label: '图像', icon: Image, color: 'from-amber-500 to-orange-500' },
  { value: 'translate', label: '翻译', icon: Languages, color: 'from-cyan-500 to-blue-500' },
  { value: 'transcribe', label: '转录', icon: FileText, color: 'from-rose-500 to-pink-500' },
]

const selectClass =
  'h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500/40 hover:border-indigo-400/60'

/**
 * 历史筛选器：卡片式类型切换 + 实例下拉。
 */
export function HistoryFilter({
  typeFilter,
  instanceFilter,
  instances,
  onTypeChange,
  onInstanceChange,
}: HistoryFilterProps) {
  return (
    <div className="space-y-3">
      {/* Type filter cards */}
      <div className="flex flex-wrap gap-2">
        {TYPE_OPTIONS.map((opt) => {
          const Icon = opt.icon
          const active = typeFilter === opt.value
          return (
            <button
              key={opt.value || 'all'}
              type="button"
              onClick={() => onTypeChange(opt.value)}
              className={cn(
                'flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-all',
                active
                  ? `bg-gradient-to-r ${opt.color} text-white shadow-md`
                  : 'border bg-background text-muted-foreground hover:border-indigo-300 hover:text-foreground'
              )}
            >
              {Icon !== (() => null) && <Icon className="h-3.5 w-3.5" />}
              {opt.label}
            </button>
          )
        })}
      </div>

      {/* Instance filter */}
      <div className="flex items-center gap-3">
        <label htmlFor="instance-filter" className="text-sm text-muted-foreground">
          实例:
        </label>
        <select
          id="instance-filter"
          value={instanceFilter}
          onChange={(e) => onInstanceChange(e.target.value)}
          className={selectClass}
        >
          <option value="">全部实例</option>
          {instances.map((instance) => (
            <option key={instance.id} value={instance.id}>
              {instance.name}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
