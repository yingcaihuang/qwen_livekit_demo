/**
 * Hook that collects real-time WebRTC stats from the LiveKit Room
 * using the SDK's public track stats API and reports to the backend.
 *
 * Uses:
 * - LocalAudioTrack.getSenderStats() for publish metrics
 * - RemoteAudioTrack.getReceiverStats() for subscribe metrics
 * - room.engine.pcManager.publisher.getStats() for ICE candidate info
 */

import { useEffect, useRef } from 'react'
import {
  Room,
  LocalAudioTrack,
  RemoteAudioTrack,
  RemoteTrackPublication,
  Track,
} from 'livekit-client'
import type { AudioSenderStats, AudioReceiverStats } from 'livekit-client'

const REPORT_INTERVAL_MS = 5000 // Report every 5 seconds

interface TrackStatsReport {
  track_type: 'audio' | 'video'
  direction: 'publish' | 'subscribe'
  packet_loss_ratio: number
  rtt_ms: number
  jitter_ms: number
  bitrate_kbps: number
}

export function useWebRTCStats(
  room: Room | null,
  roomName: string,
  enabled: boolean = true
) {
  const prevSenderStatsRef = useRef<AudioSenderStats | undefined>(undefined)
  const prevReceiverStatsRef = useRef<AudioReceiverStats | undefined>(undefined)

  useEffect(() => {
    if (!enabled || !room || !roomName) {
      console.debug('[WebRTCStats] effect skip: enabled=', enabled, 'room=', !!room, 'roomName=', roomName)
      return
    }

    console.debug('[WebRTCStats] effect started, scheduling collection')

    let intervalId: ReturnType<typeof setInterval> | null = null
    let stopped = false

    async function collect() {
      if (stopped) return

      // Use the room from closure (captured when effect ran)
      if (!room || room.state !== 'connected') {
        console.debug('[WebRTCStats] collect skip: room.state=', room?.state)
        return
      }

      console.debug('[WebRTCStats] collecting stats for room:', roomName)

      const tracks: TrackStatsReport[] = []
      let iceCandidateType = 'host'
      let iceConnectionState = 'connected'

      // --- Collect publisher (outbound) stats ---
      try {
        const localPub = room.localParticipant.getTrackPublication(Track.Source.Microphone)
        const audioTrack = localPub?.audioTrack
        if (audioTrack && audioTrack instanceof LocalAudioTrack) {
          const senderStats = await audioTrack.getSenderStats()
          if (senderStats) {
            const prev = prevSenderStatsRef.current
            let bitrateKbps = 0
            if (prev && senderStats.timestamp > prev.timestamp) {
              const deltaBytes = (senderStats.bytesSent || 0) - (prev.bytesSent || 0)
              const deltaSec = (senderStats.timestamp - prev.timestamp) / 1000
              bitrateKbps = deltaSec > 0 ? (deltaBytes * 8) / deltaSec / 1000 : 0
            }

            const packetsSent = senderStats.packetsSent || 0
            const packetsLost = senderStats.packetsLost || 0
            const lossRatio = packetsSent > 0
              ? packetsLost / (packetsSent + packetsLost)
              : 0

            tracks.push({
              track_type: 'audio',
              direction: 'publish',
              packet_loss_ratio: Math.max(0, Math.round(lossRatio * 10000) / 10000),
              rtt_ms: Math.round((senderStats.roundTripTime || 0) * 1000 * 10) / 10,
              jitter_ms: Math.round((senderStats.jitter || 0) * 1000 * 10) / 10,
              bitrate_kbps: Math.round(bitrateKbps * 10) / 10,
            })

            prevSenderStatsRef.current = senderStats
          }
        }
      } catch (e) {
        console.debug('[WebRTCStats] publisher stats error:', e)
      }

      // --- Collect subscriber (inbound) stats ---
      try {
        for (const [, participant] of room.remoteParticipants) {
          for (const [, pub] of participant.audioTrackPublications) {
            const remotePub = pub as RemoteTrackPublication
            const track = remotePub.track
            if (track && track instanceof RemoteAudioTrack) {
              const receiverStats = await track.getReceiverStats()
              if (receiverStats) {
                const prev = prevReceiverStatsRef.current
                let bitrateKbps = 0
                if (prev && receiverStats.timestamp > prev.timestamp) {
                  const deltaBytes = (receiverStats.bytesReceived || 0) - (prev.bytesReceived || 0)
                  const deltaSec = (receiverStats.timestamp - prev.timestamp) / 1000
                  bitrateKbps = deltaSec > 0 ? (deltaBytes * 8) / deltaSec / 1000 : 0
                }

                const packetsReceived = receiverStats.packetsReceived || 0
                const packetsLost = receiverStats.packetsLost || 0
                const lossRatio = packetsReceived > 0
                  ? packetsLost / (packetsReceived + packetsLost)
                  : 0

                tracks.push({
                  track_type: 'audio',
                  direction: 'subscribe',
                  packet_loss_ratio: Math.max(0, Math.round(lossRatio * 10000) / 10000),
                  rtt_ms: 0,
                  jitter_ms: Math.round((receiverStats.jitter || 0) * 1000 * 10) / 10,
                  bitrate_kbps: Math.round(bitrateKbps * 10) / 10,
                })

                prevReceiverStatsRef.current = receiverStats
              }
              break
            }
          }
          break
        }
      } catch (e) {
        console.debug('[WebRTCStats] subscriber stats error:', e)
      }

      // --- Get ICE candidate info ---
      try {
        const engine = (room as any).engine
        const pcManager = engine?.pcManager
        if (pcManager?.publisher) {
          const rtcStats: RTCStatsReport = await pcManager.publisher.getStats()
          rtcStats.forEach((report: any) => {
            if (report.type === 'candidate-pair' && report.state === 'succeeded') {
              iceConnectionState = 'connected'
              const localCandidateId = report.localCandidateId
              if (localCandidateId) {
                const localCandidate = rtcStats.get(localCandidateId)
                if (localCandidate?.candidateType) {
                  iceCandidateType = localCandidate.candidateType
                }
              }
            }
          })
        }
      } catch {
        // pcManager may not be accessible
      }

      if (tracks.length === 0) {
        console.debug('[WebRTCStats] no tracks collected')
        return
      }

      const identity = room.localParticipant?.identity || 'user'
      console.debug('[WebRTCStats] reporting', tracks.length, 'tracks for', identity, tracks)

      // Report to backend
      try {
        await fetch('/internal/monitor/webrtc-stats', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            room_name: roomName,
            identity,
            ice_candidate_type: iceCandidateType,
            ice_connection_state: iceConnectionState,
            tracks,
          }),
        })
      } catch {
        // Non-critical
      }
    }

    // Start after a short delay to let PeerConnection stabilize
    const startTimeout = setTimeout(() => {
      collect()
      intervalId = setInterval(collect, REPORT_INTERVAL_MS)
    }, 3000)

    return () => {
      stopped = true
      clearTimeout(startTimeout)
      if (intervalId) clearInterval(intervalId)
    }
  }, [enabled, room, roomName])
}
