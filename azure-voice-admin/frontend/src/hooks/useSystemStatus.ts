import { useEffect, useState } from 'react'

interface SystemStatus {
  livekit_connected: boolean
  avx2_supported: boolean
  realtime_available: boolean
}

export function useSystemStatus() {
  const [status, setStatus] = useState<SystemStatus | null>(null)

  useEffect(() => {
    fetch('/api/health', { credentials: 'include' })
      .then(r => r.json())
      .then(setStatus)
      .catch(() => {})
  }, [])

  return status
}
