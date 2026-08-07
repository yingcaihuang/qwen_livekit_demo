import { Filter } from 'lucide-react'
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

const TYPE_OPTIONS: { value: HistoryTypeFilter; label: string }[] = [
  { value: '', label: '全部类型' },
  { value: 'voice', label: '语音' },
  { value: 'chat', label: '对话' },
  { value: 'image', label: '图像' },
]

const selectClass =
  'h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500/40 hover:border-indigo-400/60'

/**
 * 历史筛选器：类型（全部/语音/对话/图像）+ 实例下拉，
 * 沿用彩色渐变背景的视觉风格。
 */
export function HistoryFilter({
  typeFilter,
  instanceFilter,
  instances,
  onTypeChange,
  onInstanceChange,
}: HistoryFilterProps) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border bg-gradient-to-r from-muted/50 to-transparent px-4 py-3 shadow-sm">
      <span className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
        <Filter className="h-4 w-4 text-indigo-500" aria-hidden="true" />
        筛选:
      </span>

      <label htmlFor="type-filter" className="sr-only">
        按类型筛选
      </label>
      <select
        id="type-filter"
        value={typeFilter}
        onChange={(e) => onTypeChange(e.target.value as HistoryTypeFilter)}
        className={selectClass}
      >
        {TYPE_OPTIONS.map((opt) => (
          <option key={opt.value || 'all'} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      <label htmlFor="instance-filter" className="sr-only">
        按实例筛选
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
  )
}
