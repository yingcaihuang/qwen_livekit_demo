import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import type { LogEntry } from '@/types'

interface UseSessionLogsResult {
  logs: LogEntry[]
  filteredLogs: LogEntry[]
  isConnected: boolean
  filter: string
  setFilter: (eventType: string) => void
  clearLogs: () => void
}

const MAX_RETRIES = 3
const RETRY_DELAYS = [1000, 2000, 4000] // escalating retry delays

export function useSessionLogs(sessionId: string | null): UseSessionLogsResult {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [filter, setFilter] = useState<string>('all')
  const wsRef = useRef<WebSocket | null>(null)
  const retriesRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const connect = useCallback(() => {
    if (!sessionId) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const url = `${protocol}//${host}/ws/sessions/${sessionId}/logs`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
      retriesRef.current = 0
    }

    ws.onmessage = (event) => {
      try {
        const logEntry = JSON.parse(event.data) as LogEntry
        setLogs((prev) => [...prev, logEntry])
      } catch {
        // ignore malformed messages
      }
    }

    ws.onclose = () => {
      setIsConnected(false)
      wsRef.current = null

      // Auto-reconnect with max retries
      if (retriesRef.current < MAX_RETRIES) {
        const delay = RETRY_DELAYS[retriesRef.current] || 4000
        retryTimerRef.current = setTimeout(() => {
          retriesRef.current += 1
          connect()
        }, delay)
      }
    }

    ws.onerror = () => {
      // onclose will fire after onerror, reconnect logic is there
    }
  }, [sessionId])

  useEffect(() => {
    if (!sessionId) return

    connect()

    return () => {
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current)
        retryTimerRef.current = null
      }
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [sessionId, connect])

  const clearLogs = useCallback(() => {
    setLogs([])
  }, [])

  const filteredLogs = useMemo(() => {
    if (filter === 'all') return logs
    return logs.filter((log) => {
      // Support wildcard matching like "session.*" or "response.*"
      if (filter.endsWith('.*')) {
        const prefix = filter.slice(0, -2)
        return log.event_type.startsWith(prefix + '.')
      }
      return log.event_type === filter
    })
  }, [logs, filter])

  return {
    logs,
    filteredLogs,
    isConnected,
    filter,
    setFilter,
    clearLogs,
  }
}
