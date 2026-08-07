import { useMemo } from 'react'
import type { LogEntry } from '@/types'

interface LogFilterProps {
  logs: LogEntry[]
  filter: string
  onFilterChange: (value: string) => void
}

const PRESET_FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'session.*', label: 'session.*' },
  { value: 'response.*', label: 'response.*' },
  { value: 'error', label: 'error' },
  { value: 'input_audio_buffer.*', label: 'input_audio_buffer.*' },
  { value: 'conversation.*', label: 'conversation.*' },
]

export function LogFilter({ logs, filter, onFilterChange }: LogFilterProps) {
  // Count entries per filter category
  const counts = useMemo(() => {
    const result: Record<string, number> = { all: logs.length }
    for (const preset of PRESET_FILTERS) {
      if (preset.value === 'all') continue
      if (preset.value.endsWith('.*')) {
        const prefix = preset.value.slice(0, -2)
        result[preset.value] = logs.filter((l) =>
          l.event_type.startsWith(prefix + '.')
        ).length
      } else {
        result[preset.value] = logs.filter(
          (l) => l.event_type === preset.value
        ).length
      }
    }
    return result
  }, [logs])

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="log-filter" className="text-sm text-muted-foreground shrink-0">
        Filter:
      </label>
      <select
        id="log-filter"
        value={filter}
        onChange={(e) => onFilterChange(e.target.value)}
        className="h-8 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
      >
        {PRESET_FILTERS.map((preset) => (
          <option key={preset.value} value={preset.value}>
            {preset.label} ({counts[preset.value] ?? 0})
          </option>
        ))}
      </select>
    </div>
  )
}
