import { useState } from 'react'
import { ArrowRight, ArrowLeft, Circle, ChevronDown, ChevronRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { LogEntry } from '@/types'

interface LogEntryComponentProps {
  entry: LogEntry
}

function formatTimestamp(timestamp: string): string {
  try {
    const date = new Date(timestamp)
    const hours = String(date.getHours()).padStart(2, '0')
    const minutes = String(date.getMinutes()).padStart(2, '0')
    const seconds = String(date.getSeconds()).padStart(2, '0')
    const ms = String(date.getMilliseconds()).padStart(3, '0')
    return `${hours}:${minutes}:${seconds}.${ms}`
  } catch {
    return timestamp
  }
}

function getDirectionIcon(direction: string) {
  switch (direction) {
    case 'outbound':
      return <ArrowRight className="h-3.5 w-3.5 text-blue-500" />
    case 'inbound':
      return <ArrowLeft className="h-3.5 w-3.5 text-green-500" />
    default:
      return <Circle className="h-3 w-3 text-gray-400" />
  }
}

function getPayloadPreview(payload: string, maxLength = 80): string {
  try {
    const parsed = JSON.parse(payload)
    const str = JSON.stringify(parsed)
    if (str.length <= maxLength) return str
    return str.slice(0, maxLength) + '...'
  } catch {
    if (payload.length <= maxLength) return payload
    return payload.slice(0, maxLength) + '...'
  }
}

function formatPayload(payload: string): string {
  try {
    const parsed = JSON.parse(payload)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return payload
  }
}

function isErrorEntry(eventType: string): boolean {
  return eventType.toLowerCase().includes('error')
}

export function LogEntryComponent({ entry }: LogEntryComponentProps) {
  const [expanded, setExpanded] = useState(false)
  const isError = isErrorEntry(entry.event_type)

  return (
    <div
      className={cn(
        'border-l-2 px-3 py-2 cursor-pointer hover:bg-muted/50 transition-colors',
        isError ? 'border-l-red-500 bg-red-50 dark:bg-red-950/20' : 'border-l-transparent',
      )}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-center gap-2 text-sm">
        {/* Expand/collapse indicator */}
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        )}

        {/* Timestamp */}
        <span className="font-mono text-xs text-muted-foreground shrink-0">
          {formatTimestamp(entry.timestamp)}
        </span>

        {/* Direction icon */}
        <span className="shrink-0">{getDirectionIcon(entry.direction)}</span>

        {/* Event type badge */}
        <Badge
          variant={isError ? 'destructive' : 'secondary'}
          className="shrink-0 text-xs"
        >
          {entry.event_type}
        </Badge>

        {/* Payload preview */}
        <span className="font-mono text-xs text-muted-foreground truncate">
          {getPayloadPreview(entry.payload)}
        </span>
      </div>

      {/* Expanded payload */}
      {expanded && (
        <div className="mt-2 ml-6">
          <pre className="text-xs font-mono bg-muted p-3 rounded-md overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap break-all">
            {formatPayload(entry.payload)}
          </pre>
        </div>
      )}
    </div>
  )
}
