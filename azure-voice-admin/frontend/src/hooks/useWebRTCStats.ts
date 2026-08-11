/**
 * Hook that collects real-time WebRTC stats from the LiveKit Room's
 * RTCPeerConnection and periodically reports them to the backend.
 *
 * Uses the standard WebRTC getStats() API to extract:
 * - Packet loss ratio (from inbound/outbound-rtp reports)
 * - Round-trip time (from candidate-pair or remote-inbound-rtp)
 * - Jitter (from inbound-rtp)
 * - Bitrate (calculated from bytes sent/received delta)
 * - ICE candidate type and connection state
 */

import { useEffect, useRef, useCallback } from 'react'
import type { Room } from 'livekit-client'

const REPORT_INTERVAL_MS = 5000 // Report every 5 seconds

interface TrackStatsReport {
  track_type: 'audio' | 'video'
  direction: 'publish' | 'subscribe'
  packet_loss_ratio: number
  rtt_ms: number
  jitter_ms: number
  bitrate_kbps: number
}

interface PrevBytes {
  timestamp: number
  bytesSent: number
  bytesReceived: number
}

export function useWebRTCStats(
  room: Room | null,
  roomName: string,
  enabled: boolean = true
) {
  const prevBytesRef = useRef<Map<string, PrevBytes>>(new Map())
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const collectAndReport = useCallback(async () => {
    if (!room || !roomName) return

    // Access the internal PeerConnections via room.engine
    // livekit-client exposes publisher and subscriber PeerConnections
    const engine = (room as any).engine
    if (!engine) return

    const tracks: TrackStatsReport[] = []
    let iceCandidateType = 'host'
    let iceConnectionState = 'unknown'

    // Collect publisher stats (outbound - our mic audio)
    try {
      const publisherPc: RTCPeerConnection | undefined =
        engine.publisher?.pc || engine.pcManager?.publisher?.pc
      if (publisherPc) {
        iceConnectionState = publisherPc.iceConnectionState || 'unknown'
        const stats = await publisherPc.getStats()
        const pubTrack = extractOutboundStats(stats, prevBytesRef.current)
        if (pubTrack) tracks.push(pubTrack)

        // Get ICE candidate type from the active candidate pair
        const iceInfo = extractIceCandidateInfo(stats)
        if (iceInfo.candidateType) iceCandidateType = iceInfo.candidateType
      }
    } catch {
      // PeerConnection may not be ready yet
    }

    // Collect subscriber stats (inbound - agent's audio)
    try {
      const subscriberPc: RTCPeerConnection | undefined =
        engine.subscriber?.pc || engine.pcManager?.subscriber?.pc
      if (subscriberPc) {
        if (iceConnectionState === 'unknown') {
          iceConnectionState = subscriberPc.iceConnectionState || 'unknown'
        }
        const stats = await subscriberPc.getStats()
        const subTrack = extractInboundStats(stats, prevBytesRef.current)
        if (subTrack) tracks.push(subTrack)

        // Fallback ICE info from subscriber if publisher didn't have it
        if (iceCandidateType === 'host') {
          const iceInfo = extractIceCandidateInfo(stats)
          if (iceInfo.candidateType) iceCandidateType = iceInfo.candidateType
        }
      }
    } catch {
      // PeerConnection may not be ready yet
    }

    if (tracks.length === 0) return

    // Get participant identity
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
      // Non-critical, don't crash the session
    }
  }, [room, roomName])

  useEffect(() => {
    if (!enabled || !room || !roomName) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
      return
    }

    // Start periodic collection
    intervalRef.current = setInterval(collectAndReport, REPORT_INTERVAL_MS)

    // Collect immediately on start
    collectAndReport()

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [enabled, room, roomName, collectAndReport])
}

// ---------------------------------------------------------------------------
// Stats extraction helpers
// ---------------------------------------------------------------------------

function extractOutboundStats(
  stats: RTCStatsReport,
  prevBytes: Map<string, PrevBytes>
): TrackStatsReport | null {
  let packetsSent = 0
  let packetsLost = 0
  let rttMs = 0
  let jitterMs = 0
  let bytesSent = 0
  let timestamp = 0
  let found = false
  let trackType: 'audio' | 'video' = 'audio'

  stats.forEach((report) => {
    if (report.type === 'outbound-rtp' && report.kind === 'audio') {
      found = true
      trackType = 'audio'
      packetsSent = report.packetsSent || 0
      bytesSent = report.bytesSent || 0
      timestamp = report.timestamp || Date.now()

      // RTT from remote-inbound-rtp linked via remoteId
      if (report.remoteId) {
        const remote = stats.get(report.remoteId)
        if (remote) {
          rttMs = (remote.roundTripTime || 0) * 1000
          packetsLost = remote.packetsLost || 0
          jitterMs = (remote.jitter || 0) * 1000
        }
      }
    }
  })

  if (!found) return null

  // Calculate bitrate from bytes delta
  const key = 'outbound-audio'
  const prev = prevBytes.get(key)
  let bitrateKbps = 0
  if (prev && timestamp > prev.timestamp) {
    const deltaBits = (bytesSent - prev.bytesSent) * 8
    const deltaSec = (timestamp - prev.timestamp) / 1000
    bitrateKbps = deltaSec > 0 ? deltaBits / deltaSec / 1000 : 0
  }
  prevBytes.set(key, { timestamp, bytesSent, bytesReceived: 0 })

  const lossRatio =
    packetsSent > 0 ? packetsLost / (packetsSent + packetsLost) : 0

  return {
    track_type: trackType,
    direction: 'publish',
    packet_loss_ratio: Math.max(0, lossRatio),
    rtt_ms: Math.round(rttMs * 10) / 10,
    jitter_ms: Math.round(jitterMs * 10) / 10,
    bitrate_kbps: Math.round(bitrateKbps * 10) / 10,
  }
}

function extractInboundStats(
  stats: RTCStatsReport,
  prevBytes: Map<string, PrevBytes>
): TrackStatsReport | null {
  let packetsReceived = 0
  let packetsLost = 0
  let jitterMs = 0
  let bytesReceived = 0
  let timestamp = 0
  let found = false
  let trackType: 'audio' | 'video' = 'audio'

  stats.forEach((report) => {
    if (report.type === 'inbound-rtp' && report.kind === 'audio') {
      found = true
      trackType = 'audio'
      packetsReceived = report.packetsReceived || 0
      packetsLost = report.packetsLost || 0
      jitterMs = (report.jitter || 0) * 1000
      bytesReceived = report.bytesReceived || 0
      timestamp = report.timestamp || Date.now()
    }
  })

  if (!found) return null

  // Calculate bitrate from bytes delta
  const key = 'inbound-audio'
  const prev = prevBytes.get(key)
  let bitrateKbps = 0
  if (prev && timestamp > prev.timestamp) {
    const deltaBits = (bytesReceived - prev.bytesReceived) * 8
    const deltaSec = (timestamp - prev.timestamp) / 1000
    bitrateKbps = deltaSec > 0 ? deltaBits / deltaSec / 1000 : 0
  }
  prevBytes.set(key, { timestamp, bytesSent: 0, bytesReceived })

  const lossRatio =
    packetsReceived > 0 ? packetsLost / (packetsReceived + packetsLost) : 0

  // RTT for inbound: check candidate-pair stats
  let rttMs = 0
  stats.forEach((report) => {
    if (
      report.type === 'candidate-pair' &&
      report.state === 'succeeded' &&
      report.currentRoundTripTime
    ) {
      rttMs = report.currentRoundTripTime * 1000
    }
  })

  return {
    track_type: trackType,
    direction: 'subscribe',
    packet_loss_ratio: Math.max(0, lossRatio),
    rtt_ms: Math.round(rttMs * 10) / 10,
    jitter_ms: Math.round(jitterMs * 10) / 10,
    bitrate_kbps: Math.round(bitrateKbps * 10) / 10,
  }
}

function extractIceCandidateInfo(stats: RTCStatsReport): {
  candidateType: string | null
} {
  let candidateType: string | null = null

  stats.forEach((report) => {
    // Look for the active candidate pair
    if (report.type === 'candidate-pair' && report.state === 'succeeded') {
      const localCandidateId = report.localCandidateId
      if (localCandidateId) {
        const localCandidate = stats.get(localCandidateId)
        if (localCandidate && localCandidate.candidateType) {
          candidateType = localCandidate.candidateType // "host", "srflx", "relay"
        }
      }
    }
  })

  return { candidateType }
}
