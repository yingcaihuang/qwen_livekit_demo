import { cn } from '@/lib/utils'
import type { ConnectionState } from '@/types'

interface ConnectionStatusProps {
  state: ConnectionState
  instanceName?: string
}

const STATUS_CONFIG: Record<ConnectionState, { label: string; color: string; dotColor: string }> = {
  idle: {
    label: 'Idle',
    color: 'text-muted-foreground',
    dotColor: 'bg-gray-400',
  },
  connecting: {
    label: 'Connecting...',
    color: 'text-yellow-600',
    dotColor: 'bg-yellow-500 animate-pulse',
  },
  connected: {
    label: 'Connected',
    color: 'text-green-600',
    dotColor: 'bg-green-500',
  },
  agent_speaking: {
    label: 'Agent Speaking',
    color: 'text-blue-600',
    dotColor: 'bg-blue-500 animate-pulse',
  },
  user_speaking: {
    label: 'User Speaking',
    color: 'text-purple-600',
    dotColor: 'bg-purple-500 animate-pulse',
  },
  disconnected: {
    label: 'Disconnected',
    color: 'text-red-600',
    dotColor: 'bg-red-500',
  },
}

export function ConnectionStatus({ state, instanceName }: ConnectionStatusProps) {
  const config = STATUS_CONFIG[state]

  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-2">
        <span className={cn('inline-block h-2.5 w-2.5 rounded-full', config.dotColor)} />
        <span className={cn('text-sm font-medium', config.color)}>
          {config.label}
        </span>
      </div>
      {instanceName && (
        <span className="text-xs text-muted-foreground">
          Instance: <span className="font-medium">{instanceName}</span>
        </span>
      )}
    </div>
  )
}
