import { useState, useRef, useCallback, useEffect } from 'react'
import {
  Room,
  RoomEvent,
  Track,
  ConnectionState,
  createLocalTracks,
  RemoteTrackPublication,
  RemoteTrack,
  Participant,
} from 'livekit-client'
import type { ConnectionState as AppConnectionState } from '@/types'

interface UseLiveKitParams {
  token: string
  url: string
  autoConnect?: boolean
}

interface UseLiveKitResult {
  room: Room | null
  connectionState: AppConnectionState
  connect: () => Promise<void>
  disconnect: () => void
  isMicEnabled: boolean
  toggleMic: () => Promise<void>
}

export function useLiveKit({ token, url, autoConnect = false }: UseLiveKitParams): UseLiveKitResult {
  const [connectionState, setConnectionState] = useState<AppConnectionState>('idle')
  const [isMicEnabled, setIsMicEnabled] = useState(true)
  const roomRef = useRef<Room | null>(null)
  const audioElementRef = useRef<HTMLAudioElement | null>(null)

  const connect = useCallback(async () => {
    if (roomRef.current?.state === ConnectionState.Connected) return

    setConnectionState('connecting')

    const room = new Room()
    roomRef.current = room

    // Handle connection events
    room.on(RoomEvent.Connected, () => {
      setConnectionState('connected')
    })

    room.on(RoomEvent.Disconnected, () => {
      setConnectionState('disconnected')
      roomRef.current = null
    })

    room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack, _pub: RemoteTrackPublication, _participant: Participant) => {
      if (track.kind === Track.Kind.Audio) {
        // Attach remote audio track to a hidden audio element for playback
        if (!audioElementRef.current) {
          audioElementRef.current = document.createElement('audio')
          audioElementRef.current.autoplay = true
          document.body.appendChild(audioElementRef.current)
        }
        track.attach(audioElementRef.current)
      }
    })

    room.on(RoomEvent.ActiveSpeakersChanged, (speakers: Participant[]) => {
      if (room.state !== ConnectionState.Connected) return

      const localParticipant = room.localParticipant
      const localIsSpeaking = speakers.some(
        (s) => s.identity === localParticipant.identity
      )
      const remoteIsSpeaking = speakers.some(
        (s) => s.identity !== localParticipant.identity
      )

      if (remoteIsSpeaking) {
        setConnectionState('agent_speaking')
      } else if (localIsSpeaking) {
        setConnectionState('user_speaking')
      } else {
        setConnectionState('connected')
      }
    })

    try {
      // Create and publish local microphone track
      const tracks = await createLocalTracks({ audio: true, video: false })
      await room.connect(url, token)

      for (const track of tracks) {
        await room.localParticipant.publishTrack(track)
      }
      setIsMicEnabled(true)
    } catch (error) {
      console.error('Failed to connect to LiveKit room:', error)
      setConnectionState('disconnected')
      roomRef.current = null
    }
  }, [token, url])

  const disconnect = useCallback(() => {
    if (roomRef.current) {
      roomRef.current.disconnect()
      roomRef.current = null
    }
    // Clean up audio element
    if (audioElementRef.current) {
      audioElementRef.current.remove()
      audioElementRef.current = null
    }
    setConnectionState('disconnected')
  }, [])

  const toggleMic = useCallback(async () => {
    if (!roomRef.current) return
    const localParticipant = roomRef.current.localParticipant
    const enabled = localParticipant.isMicrophoneEnabled
    await localParticipant.setMicrophoneEnabled(!enabled)
    setIsMicEnabled(!enabled)
  }, [])

  // Auto-connect if requested
  useEffect(() => {
    if (autoConnect && token && url) {
      connect()
    }
  }, [autoConnect, token, url, connect])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (roomRef.current) {
        roomRef.current.disconnect()
        roomRef.current = null
      }
      if (audioElementRef.current) {
        audioElementRef.current.remove()
        audioElementRef.current = null
      }
    }
  }, [])

  return {
    room: roomRef.current,
    connectionState,
    connect,
    disconnect,
    isMicEnabled,
    toggleMic,
  }
}
