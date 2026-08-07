import { useEffect, useRef } from 'react'
import { Trash2, Wifi, WifiOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useSessionLogs } from '@/hooks/useSessionLogs'
import { LogEntryComponent } from './LogEntry'
import { LogFilter } from './LogFilter'

interface DebugConsoleProps {
  sessionId: string
  isActive: boolean
}

export function DebugConsole({ sessionId, isActive }: DebugConsoleProps) {
  const { logs, filteredLogs, isConnected, filter, setFilter, clearLogs } =
    useSessionLogs(isActive ? sessionId : null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when new entries arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [filteredLogs.length])

  return (
    <div className="flex flex-col h-full border rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/30">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-medium">Debug Console</h3>
          {/* Connection status indicator */}
          <div className="flex items-center gap-1.5">
            {isConnected ? (
              <>
                <Wifi className="h-3.5 w-3.5 text-green-500" />
                <span className="text-xs text-green-600">Connected</span>
              </>
            ) : (
              <>
                <WifiOff className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs text-muted-foreground">Disconnected</span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <LogFilter logs={logs} filter={filter} onFilterChange={setFilter} />
          <Button
            variant="ghost"
            size="sm"
            onClick={clearLogs}
            className="h-8"
            title="Clear logs"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Log entries */}
      <div
        ref={scrollRef}
        className={cn(
          'flex-1 overflow-y-auto divide-y',
          filteredLogs.length === 0 && 'flex items-center justify-center',
        )}
      >
        {filteredLogs.length === 0 ? (
          <div className="text-sm text-muted-foreground text-center p-4">
            {isActive
              ? 'Waiting for log entries...'
              : 'Session is not active. No live logs available.'}
          </div>
        ) : (
          filteredLogs.map((entry, index) => (
            <LogEntryComponent key={entry.id || index} entry={entry} />
          ))
        )}
      </div>

      {/* Footer with entry count */}
      <div className="px-4 py-1.5 border-t bg-muted/30 text-xs text-muted-foreground">
        {filteredLogs.length} / {logs.length} entries
      </div>
    </div>
  )
}
