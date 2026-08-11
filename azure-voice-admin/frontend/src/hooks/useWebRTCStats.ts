/**
 * Hook that collects real-time WebRTC stats from the LiveKit Room
 * using the SDK's public track stats API and reports to the backend.
 *
 * Uses:
 * - LocalAudioTrack.getSenderStats() for publish metrics
 * - RemoteAudioTrack.getReceiverStats() for subscribe metrics
 * - room.engine.pcManager.publisher.getStats() for ICE info + RTT
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
  const prevSenderRef = useRef<AudioSenderStats | undefined>(undefined)
  const prevReceiverRef = useRef<AudioReceiverStats | undefined>(undefined)

  useEffect(() => {
    if (!enabled || !room || !roomName) return

    let intervalId: ReturnType<typeof setInterval> | null = null
    let stopped = false

    async function collect() {
      if (stopped || !room || room.state !== 'connected') return

      const tracks: TrackStatsReport[] = []
      let iceCandidateType = 'host'
      let iceConnectionState = 'connected'
      let rttFromIce = 0 // RTT from ICE candidate-pair (most reliable source)

      // --- Step 1: Get ICE info + RTT from candidate-pair ---
      // This is the most reliable RTT source (STUN-based measurement)
      try {
        const engine = (room as any).engine
        const pcManager = engine?.pcManager
        if (pcManager?.publisher) {
          const rtcStats: RTCStatsReport = await pcManager.publisher.getStats()
          rtcStats.forEach((report: any) => {
            if (report.type === 'candidate-pair' && report.state === 'succeeded') {
              iceConnectionState = 'connected'
              // currentRoundTripTime is in seconds
              if (report.currentRoundTripTime != null) {
                rttFromIce = report.currentRoundTripTime * 1000
              }
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

      // --- Step 2: Collect publisher (outbound) stats ---
      try {
        const localPub = room.localParticipant.getTrackPublication(Track.Source.Microphone)
        const audioTrack = localPub?.audioTrack
        if (audioTrack && audioTrack instanceof LocalAudioTrack) {
          const stats = await audioTrack.getSenderStats()
          if (stats) {
            const prev = prevSenderRef.current

            // Bitrate: incremental bytes delta
            let bitrateKbps = 0
            if (prev && stats.timestamp > prev.timestamp) {
              const deltaBytes = (stats.bytesSent || 0) - (prev.bytesSent || 0)
              const deltaSec = (stats.timestamp - prev.timestamp) / 1000
              bitrateKbps = deltaSec > 0 ? (deltaBytes * 8) / deltaSec / 1000 : 0
            }

            // Packet loss: incremental (delta lost / delta sent)
            let lossRatio = 0
            if (prev) {
              const deltaSent = (stats.packetsSent || 0) - (prev.packetsSent || 0)
              const deltaLost = (stats.packetsLost || 0) - (prev.packetsLost || 0)
              if (deltaSent > 0) {
                lossRatio = Math.max(0, deltaLost / (deltaSent + deltaLost))
              }
            }

            // RTT: prefer SDK value, fallback to ICE RTT
            const rttMs = (stats.roundTripTime && stats.roundTripTime > 0)
              ? stats.roundTripTime * 1000
              : rttFromIce

            tracks.push({
              track_type: 'audio',
              direction: 'publish',
              packet_loss_ratio: Math.round(lossRatio * 10000) / 10000,
              rtt_ms: Math.round(rttMs * 10) / 10,
              jitter_ms: Math.round((stats.jitter || 0) * 1000 * 10) / 10,
              bitrate_kbps: Math.round(bitrateKbps * 10) / 10,
            })

            prevSenderRef.current = stats
          }
        }
      } catch {
        // Track may not be ready
      }

      // --- Step 3: Collect subscriber (inbound) stats ---
      try {
        for (const [, participant] of room.remoteParticipants) {
          for (const [, pub] of participant.audioTrackPublications) {
            const remotePub = pub as RemoteTrackPublication
            const track = remotePub.track
            if (track && track instanceof RemoteAudioTrack) {
              const stats = await track.getReceiverStats()
              if (stats) {
                const prev = prevReceiverRef.current

                // Bitrate: incremental
                let bitrateKbps = 0
                if (prev && stats.timestamp > prev.timestamp) {
                  const deltaBytes = (stats.bytesReceived || 0) - (prev.bytesReceived || 0)
                  const deltaSec = (stats.timestamp - prev.timestamp) / 1000
                  bitrateKbps = deltaSec > 0 ? (deltaBytes * 8) / deltaSec / 1000 : 0
                }

                // Packet loss: incremental
                let lossRatio = 0
                if (prev) {
                  const deltaRecv = (stats.packetsReceived || 0) - (prev.packetsReceived || 0)
                  const deltaLost = (stats.packetsLost || 0) - (prev.packetsLost || 0)
                  if (deltaRecv > 0) {
                    lossRatio = Math.max(0, deltaLost / (deltaRecv + deltaLost))
                  }
                }

                tracks.push({
                  track_type: 'audio',
                  direction: 'subscribe',
                  packet_loss_ratio: Math.round(lossRatio * 10000) / 10000,
                  rtt_ms: Math.round(rttFromIce * 10) / 10, // Use ICE RTT for inbound
                  jitter_ms: Math.round((stats.jitter || 0) * 1000 * 10) / 10,
                  bitrate_kbps: Math.round(bitrateKbps * 10) / 10,
                })

                prevReceiverRef.current = stats
              }
              break // First remote audio track only
            }
          }
          break // First remote participant only
        }
      } catch {
        // Track may not be ready
      }

      if (tracks.length === 0) return

      const identity = room.localParticipant?.identity || 'user'

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
