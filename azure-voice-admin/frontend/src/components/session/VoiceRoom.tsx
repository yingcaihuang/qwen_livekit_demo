import { Mic, MicOff, Phone, PhoneOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ConnectionStatus } from './ConnectionStatus'
import type { ConnectionState } from '@/types'

interface VoiceRoomProps {
  connectionState: ConnectionState
  instanceName: string
  isMicEnabled: boolean
  onStartSession: () => void
  onEndSession: () => void
  onToggleMic: () => void
  isStarting: boolean
  voiceName?: string
}

export function VoiceRoom({
  connectionState,
  instanceName,
  isMicEnabled,
  onStartSession,
  onEndSession,
  onToggleMic,
  isStarting,
  voiceName,
}: VoiceRoomProps) {
  const isConnected =
    connectionState === 'connected' ||
    connectionState === 'agent_speaking' ||
    connectionState === 'user_speaking'

  const isIdle = connectionState === 'idle' || connectionState === 'disconnected'

  return (
    <div className="flex flex-col h-full border rounded-lg overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b bg-muted/30">
        <h3 className="text-sm font-medium mb-2">Voice Room</h3>
        <ConnectionStatus state={connectionState} instanceName={instanceName} />
        {voiceName && isConnected && (
          <p className="text-xs text-muted-foreground mt-1">
            Voice: <span className="font-medium capitalize">{voiceName}</span>
          </p>
        )}
      </div>

      {/* Main area */}
      <div className="flex-1 flex flex-col items-center justify-center gap-6 p-6">
        {/* Microphone visualization area */}
        <div className="flex flex-col items-center gap-4">
          {isConnected && (
            <div className="relative">
              <div
                className={`w-24 h-24 rounded-full flex items-center justify-center transition-all ${
                  connectionState === 'user_speaking'
                    ? 'bg-purple-100 ring-4 ring-purple-300 animate-pulse'
                    : connectionState === 'agent_speaking'
                      ? 'bg-blue-100 ring-4 ring-blue-300 animate-pulse'
                      : 'bg-muted'
                }`}
              >
                {isMicEnabled ? (
                  <Mic className="h-10 w-10 text-foreground" />
                ) : (
                  <MicOff className="h-10 w-10 text-muted-foreground" />
                )}
              </div>
            </div>
          )}

          {isIdle && (
            <div className="text-center text-sm text-muted-foreground">
              <p>Click "Start Session" to begin a voice conversation</p>
              <p className="mt-1">with the selected Azure instance.</p>
            </div>
          )}

          {connectionState === 'connecting' && (
            <div className="text-center text-sm text-muted-foreground">
              <p>Establishing connection...</p>
            </div>
          )}
        </div>
      </div>

      {/* Controls */}
      <div className="px-4 py-3 border-t bg-muted/30 flex items-center justify-center gap-3">
        {isIdle && (
          <Button onClick={onStartSession} disabled={isStarting}>
            <Phone className="h-4 w-4" />
            {isStarting ? 'Starting...' : 'Start Session'}
          </Button>
        )}

        {isConnected && (
          <>
            <Button
              variant={isMicEnabled ? 'outline' : 'destructive'}
              size="icon"
              onClick={onToggleMic}
              title={isMicEnabled ? 'Mute microphone' : 'Unmute microphone'}
            >
              {isMicEnabled ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
            </Button>
            <Button variant="destructive" onClick={onEndSession}>
              <PhoneOff className="h-4 w-4" />
              End Session
            </Button>
          </>
        )}

        {connectionState === 'connecting' && (
          <Button variant="destructive" onClick={onEndSession}>
            <PhoneOff className="h-4 w-4" />
            Cancel
          </Button>
        )}
      </div>
    </div>
  )
}
