import * as Select from '@radix-ui/react-select'
import { Check, ChevronsUpDown, Cpu } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ModelSelectProps {
  /** 当前选中的模型名 */
  value: string
  /** 可选模型列表 */
  options: string[]
  /** 选择变更回调 */
  onChange: (value: string) => void
  /** 是否禁用交互 */
  disabled?: boolean
}

/**
 * 模型选择器。
 * - 当仅有一个模型时，渲染为静态徽章（无下拉交互）。
 * - 当有多个模型时，渲染为基于 Radix Select 的可访问下拉框。
 */
export function ModelSelect({ value, options, onChange, disabled }: ModelSelectProps) {
  // 单一模型：静态展示为渐变胶囊徽章，不提供交互
  if (options.length <= 1) {
    const only = options[0] ?? value
    return (
      <div
        className="inline-flex w-full items-center gap-2 rounded-lg border border-emerald-200/70 bg-gradient-to-r from-emerald-50 to-teal-50 px-3 py-2 shadow-sm dark:border-emerald-800/50 dark:from-emerald-950/40 dark:to-teal-950/40"
        title={only}
      >
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-emerald-500 to-teal-500 text-white shadow-sm">
          <Cpu className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
        <span className="truncate font-mono text-sm font-semibold text-emerald-700 dark:text-emerald-300">
          {only}
        </span>
      </div>
    )
  }

  // 多模型：Radix Select 下拉
  return (
    <Select.Root value={value} onValueChange={onChange} disabled={disabled}>
      <Select.Trigger
        className={cn(
          'group inline-flex w-full items-center gap-2 rounded-lg border border-input bg-card px-3 py-2 text-sm shadow-sm transition-colors',
          'hover:border-emerald-300 hover:bg-emerald-50/40 dark:hover:border-emerald-700 dark:hover:bg-emerald-950/20',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1',
          'disabled:cursor-not-allowed disabled:opacity-50 data-[placeholder]:text-muted-foreground'
        )}
        aria-label="选择模型"
      >
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-emerald-500 to-teal-500 text-white shadow-sm">
          <Cpu className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
        <Select.Value asChild>
          <span className="min-w-0 flex-1 truncate text-left font-mono font-semibold text-foreground">
            {value}
          </span>
        </Select.Value>
        <Select.Icon asChild>
          <ChevronsUpDown
            className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-emerald-600"
            aria-hidden="true"
          />
        </Select.Icon>
      </Select.Trigger>

      <Select.Portal>
        <Select.Content
          position="popper"
          sideOffset={6}
          className={cn(
            'z-50 max-h-[--radix-select-content-available-height] min-w-[--radix-select-trigger-width] overflow-hidden rounded-lg border border-border bg-popover text-popover-foreground shadow-lg',
            'data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95'
          )}
        >
          <Select.Viewport className="max-h-72 overflow-y-auto p-1">
            {options.map((option) => (
              <Select.Item
                key={option}
                value={option}
                className={cn(
                  'relative flex cursor-pointer select-none items-center gap-2 rounded-md py-2 pl-3 pr-8 text-sm outline-none',
                  'data-[highlighted]:bg-gradient-to-r data-[highlighted]:from-indigo-50 data-[highlighted]:to-emerald-50 data-[highlighted]:text-emerald-700',
                  'dark:data-[highlighted]:from-indigo-950/40 dark:data-[highlighted]:to-emerald-950/40 dark:data-[highlighted]:text-emerald-300',
                  'data-[state=checked]:font-semibold'
                )}
              >
                <Cpu className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                <Select.ItemText asChild>
                  <span className="min-w-0 flex-1 truncate font-mono">{option}</span>
                </Select.ItemText>
                <Select.ItemIndicator className="absolute right-2 flex items-center">
                  <Check className="h-4 w-4 text-emerald-600" aria-hidden="true" />
                </Select.ItemIndicator>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  )
}
