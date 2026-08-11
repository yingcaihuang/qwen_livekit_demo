import { Inbox } from 'lucide-react'
import { SessionRow } from './SessionRow'
import type { HistoryItem } from '@/types'

interface HistoryListProps {
  items: HistoryItem[]
  onDelete: (item: HistoryItem) => void
  selectedIds?: Set<string>
  onToggleSelect?: (id: string) => void
  onToggleAll?: () => void
}

const HEADERS = ['', '类型', '标题', '实例', '开始时间', 'Token 数量', '状态', '操作'] as const

export function SessionList({ items, onDelete, selectedIds, onToggleSelect, onToggleAll }: HistoryListProps) {
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed bg-gradient-to-br from-muted/40 to-transparent p-14 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-sky-500/10 text-sky-500">
          <Inbox className="h-8 w-8" aria-hidden="true" />
        </div>
        <p className="text-muted-foreground">暂无测试记录</p>
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-xl border shadow-sm">
      <table className="w-full">
        <thead className="bg-gradient-to-r from-muted/60 to-muted/30">
          <tr>
            <th className="w-10 px-4 py-3">
              {onToggleAll && (
                <input
                  type="checkbox"
                  checked={selectedIds ? selectedIds.size === items.length && items.length > 0 : false}
                  onChange={onToggleAll}
                  className="h-4 w-4 rounded border-gray-300"
                  aria-label="全选"
                />
              )}
            </th>
            {HEADERS.slice(1).map((header) => (
              <th
                key={header}
                className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y">
          {items.map((item) => (
            <SessionRow
              key={`${item.type}-${item.id}`}
              item={item}
              onDelete={onDelete}
              selected={selectedIds?.has(item.id) ?? false}
              onToggleSelect={onToggleSelect ? () => onToggleSelect(item.id) : undefined}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}
