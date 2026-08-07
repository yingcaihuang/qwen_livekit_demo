import { useState, useCallback, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { VoiceRoom } from '@/components/session/VoiceRoom'
import { DebugConsole } from '@/components/session/DebugConsole'
import { useLiveKit } from '@/hooks/useLiveKit'
import type { SessionResponse, Instance } from '@/types'

const VOICE_OPTIONS = [
  { value: 'alloy', label: 'Alloy - 中性平衡（默认）' },
  { value: 'ash', label: 'Ash - 温暖男声' },
  { value: 'ballad', label: 'Ballad - 柔和女声' },
  { value: 'coral', label: 'Coral - 清晰女声' },
  { value: 'echo', label: 'Echo - 深沉男声' },
  { value: 'sage', label: 'Sage - 沉稳男声' },
  { value: 'shimmer', label: 'Shimmer - 明亮女声' },
  { value: 'verse', label: 'Verse - 活力男声' },
] as const

export function VoiceSessionPage() {
  const [searchParams] = useSearchParams()
  const instanceId = searchParams.get('instance') || ''

  const [instanceName, setInstanceName] = useState<string>('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [livekitToken, setLivekitToken] = useState('')
  const [livekitUrl, setLivekitUrl] = useState('')
  const [isStarting, setIsStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedVoice, setSelectedVoice] = useState<string>('alloy')

  // Fetch instance info
  useEffect(() => {
    if (!instanceId) return
    fetch(`/api/instances/${instanceId}`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch instance')
        return res.json()
      })
      .then((data: Instance) => {
        setInstanceName(data.name)
      })
      .catch(() => {
        setInstanceName('Unknown Instance')
      })
  }, [instanceId])

  const { connectionState, connect, disconnect, isMicEnabled, toggleMic } = useLiveKit({
    token: livekitToken,
    url: livekitUrl,
    autoConnect: false,
  })

  const handleStartSession = useCallback(async () => {
    if (!instanceId) {
      setError('No instance selected. Please provide an instance ID in the URL.')
      return
    }

    setIsStarting(true)
    setError(null)

    try {
      const response = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instance_id: instanceId, voice: selectedVoice }),
      })

      if (!response.ok) {
        const errData = await response.json().catch(() => null)
        throw new Error(errData?.detail || `HTTP ${response.status}: Failed to create session`)
      }

      const data = (await response.json()) as SessionResponse
      setSessionId(data.session_id)
      setLivekitToken(data.livekit_token)
      setLivekitUrl(data.livekit_url)

      // Connect to LiveKit room after receiving token
      // We need to set state first, then connect will use them via the hook
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start session')
    } finally {
      setIsStarting(false)
    }
  }, [instanceId, selectedVoice])

  // Connect to LiveKit once we have token and url
  useEffect(() => {
    if (livekitToken && livekitUrl && connectionState === 'idle') {
      connect()
    }
  }, [livekitToken, livekitUrl, connectionState, connect])

  const handleEndSession = useCallback(async () => {
    // Disconnect from LiveKit first
    disconnect()

    // Then stop the server-side session
    if (sessionId) {
      try {
        await fetch(`/api/sessions/${sessionId}/stop`, { method: 'POST' })
      } catch {
        // Best-effort stop
      }
    }
  }, [sessionId, disconnect])

  const handleToggleMic = useCallback(async () => {
    await toggleMic()
  }, [toggleMic])

  const isSessionActive =
    connectionState === 'connecting' ||
    connectionState === 'connected' ||
    connectionState === 'agent_speaking' ||
    connectionState === 'user_speaking'

  return (
    <div className="h-full flex flex-col">
      {/* Page header */}
      <div className="px-6 py-4 border-b">
        <h1 className="text-lg font-semibold">Voice Session</h1>
        {error && (
          <p className="text-sm text-red-600 mt-1">{error}</p>
        )}
        {!instanceId && (
          <p className="text-sm text-muted-foreground mt-1">
            No instance selected. Navigate from the Instances page to start a session.
          </p>
        )}
        {instanceId && connectionState === 'idle' && (
          <div className="mt-3 flex items-center gap-3">
            <label htmlFor="voice-select" className="text-sm font-medium text-muted-foreground">
              Voice:
            </label>
            <select
              id="voice-select"
              value={selectedVoice}
              onChange={(e) => setSelectedVoice(e.target.value)}
              className="border rounded-md px-3 py-1.5 text-sm bg-background"
            >
              {VOICE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Two-column layout */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-4 p-4 min-h-0">
        {/* Left: Voice Room */}
        <div className="min-h-0">
          <VoiceRoom
            connectionState={connectionState}
            instanceName={instanceName}
            isMicEnabled={isMicEnabled}
            onStartSession={handleStartSession}
            onEndSession={handleEndSession}
            onToggleMic={handleToggleMic}
            isStarting={isStarting}
            voiceName={selectedVoice}
          />
        </div>

        {/* Right: Debug Console */}
        <div className="min-h-0">
          <DebugConsole
            sessionId={sessionId || ''}
            isActive={isSessionActive}
          />
        </div>
      </div>
    </div>
  )
}
