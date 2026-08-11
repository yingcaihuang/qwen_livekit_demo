import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, Wifi, WifiOff, Activity, Circle, ChevronDown, ChevronRight } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export interface TrackStats {
  track_type: 'audio' | 'video'
  direction: 'publish' | 'subscribe'
  packet_loss_ratio: number
  rtt_ms: number
  jitter_ms: number
  bitrate_kbps: number
}

export interface ParticipantStats {
  identity: string
  ice_candidate_type: 'host' | 'srflx' | 'relay'
  ice_connection_state: string
  tracks: TrackStats[]
}

export interface RoomStats {
  room_name: string
  participants: ParticipantStats[]
}

export interface WebRtcStatsResponse {
  rooms: RoomStats[]
  error: string | null
  timestamp: string
}

export interface UdpPortInfo {
  port: number
  bound: boolean
  recv_queue: number
  send_queue: number
  recv_packets: number | null
  send_packets: number | null
  process: string | null
}

export interface UdpPortsResponse {
  ports: UdpPortInfo[]
  port_range: { start: number; end: number }
  error: string | null
  timestamp: string
}

export interface TurnStatusResponse {
  reachable: boolean
  latency_ms: number | null
  timeout: boolean
  host: string
  port: number
  timestamp: string
}

export function UdpMonitorPage() {
  const [webrtcStats, setWebrtcStats] = useState<WebRtcStatsResponse | null>(null)
  const [udpPorts, setUdpPorts] = useState<UdpPortsResponse | null>(null)
  const [turnStatus, setTurnStatus] = useState<TurnStatusResponse | null>(null)

  const [webrtcError, setWebrtcError] = useState<string | null>(null)
  const [udpError, setUdpError] = useState<string | null>(null)
  const [turnError, setTurnError] = useState<string | null>(null)

  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const [expandedRooms, setExpandedRooms] = useState<Set<string>>(new Set())

  const fetchAll = useCallback(async () => {
    setRefreshing(true)
    try {
      const results = await Promise.allSettled([
        fetch('/api/admin/monitor/webrtc-stats', { credentials: 'include' }),
        fetch('/api/admin/monitor/udp-ports', { credentials: 'include' }),
        fetch('/api/admin/monitor/turn-status', { credentials: 'include' }),
      ])

      // WebRTC stats
      if (results[0].status === 'fulfilled' && results[0].value.ok) {
        const data = await results[0].value.json()
        setWebrtcStats(data)
        setWebrtcError(data.error || null)
      } else {
        setWebrtcError('网络错误')
      }

      // UDP ports
      if (results[1].status === 'fulfilled' && results[1].value.ok) {
        const data = await results[1].value.json()
        setUdpPorts(data)
        setUdpError(data.error || null)
      } else {
        setUdpError('网络错误')
      }

      // TURN status
      if (results[2].status === 'fulfilled' && results[2].value.ok) {
        const data = await results[2].value.json()
        setTurnStatus(data)
        setTurnError(null)
      } else {
        setTurnError('网络错误')
      }
    } catch {
      // If Promise.allSettled itself fails (shouldn't happen normally)
      setWebrtcError('网络错误')
      setUdpError('网络错误')
      setTurnError('网络错误')
    }
    setLoading(false)
    setRefreshing(false)
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  // Auto-refresh every 10 seconds
  useEffect(() => {
    const interval = setInterval(fetchAll, 10000)
    return () => clearInterval(interval)
  }, [fetchAll])

  const toggleRoom = (roomName: string) => {
    setExpandedRooms(prev => {
      const next = new Set(prev)
      if (next.has(roomName)) {
        next.delete(roomName)
      } else {
        next.add(roomName)
      }
      return next
    })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-muted-foreground">加载中...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="bg-gradient-to-r from-indigo-600 to-violet-500 bg-clip-text text-3xl font-bold tracking-tight text-transparent">
            UDP/WebRTC 传输监控
          </h1>
          <p className="text-sm text-muted-foreground">
            实时监控 WebRTC 传输质量、UDP 端口状态和 TURN/STUN 服务可达性
          </p>
        </div>
        <Button variant="outline" onClick={fetchAll} disabled={refreshing}>
          <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
          {refreshing ? '刷新中' : '刷新'}
        </Button>
      </div>

      {/* TURN/STUN Status Card */}
      <Card>
        <CardContent className="flex items-center justify-between py-4">
          {turnError ? (
            <div className="flex items-center gap-3">
              <WifiOff className="h-6 w-6 text-red-500" />
              <div>
                <p className="text-sm font-medium">TURN/STUN 服务</p>
                <p className="text-xs text-red-600">{turnError}</p>
              </div>
            </div>
          ) : turnStatus ? (
            <>
              <div className="flex items-center gap-3">
                {turnStatus.reachable ? (
                  <Wifi className="h-6 w-6 text-emerald-500" />
                ) : (
                  <WifiOff className="h-6 w-6 text-red-500" />
                )}
                <div>
                  <p className="text-sm font-medium">TURN/STUN 服务</p>
                  <p className="text-xs text-muted-foreground">
                    {turnStatus.host}:{turnStatus.port}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {turnStatus.timeout && (
                  <Badge variant="outline" className="text-xs text-amber-600 border-amber-300">
                    超时
                  </Badge>
                )}
                {turnStatus.latency_ms != null && (
                  <Badge variant="outline" className="text-xs">
                    {turnStatus.latency_ms}ms
                  </Badge>
                )}
                <Badge
                  variant={turnStatus.reachable ? 'default' : 'destructive'}
                  className="text-xs"
                >
                  {turnStatus.reachable ? '可达' : '不可达'}
                </Badge>
              </div>
            </>
          ) : null}
        </CardContent>
      </Card>

      {/* WebRTC Participant Stats Section */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Activity className="h-4 w-4 text-indigo-500" />
            WebRTC 参与者统计
          </CardTitle>
        </CardHeader>
        <CardContent>
          {webrtcError && !webrtcStats?.rooms?.length ? (
            <p className="text-sm text-red-600">{webrtcError}</p>
          ) : webrtcStats?.rooms && webrtcStats.rooms.length > 0 ? (
            <div className="space-y-3">
              {webrtcStats.rooms.map(room => (
                <div key={room.room_name} className="rounded-lg border">
                  {/* Room header - clickable to expand */}
                  <button
                    className="flex w-full items-center justify-between px-4 py-3 hover:bg-muted/30 transition-colors"
                    onClick={() => toggleRoom(room.room_name)}
                  >
                    <div className="flex items-center gap-2">
                      {expandedRooms.has(room.room_name) ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      )}
                      <span className="text-sm font-medium font-mono">{room.room_name}</span>
                    </div>
                    <Badge variant="secondary" className="text-xs">
                      {room.participants.length} 参与者
                    </Badge>
                  </button>

                  {/* Expanded participant details */}
                  {expandedRooms.has(room.room_name) && (
                    <div className="border-t px-4 py-3 space-y-4">
                      {room.participants.map(participant => (
                        <div key={participant.identity} className="space-y-2">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium">{participant.identity}</span>
                            <Badge variant="outline" className="text-[10px]">
                              ICE: {participant.ice_candidate_type}
                            </Badge>
                            <Badge
                              variant="outline"
                              className={cn(
                                "text-[10px]",
                                participant.ice_connection_state === 'connected' || participant.ice_connection_state === 'completed'
                                  ? 'text-emerald-600 border-emerald-300'
                                  : 'text-amber-600 border-amber-300'
                              )}
                            >
                              {participant.ice_connection_state}
                            </Badge>
                          </div>

                          {/* Tracks table */}
                          {participant.tracks.length > 0 && (
                            <div className="overflow-x-auto">
                              <table className="w-full text-xs">
                                <thead className="border-b bg-muted/30">
                                  <tr>
                                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">类型</th>
                                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">方向</th>
                                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">丢包率</th>
                                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">RTT</th>
                                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">抖动</th>
                                    <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">码率</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {participant.tracks.map((track, idx) => (
                                    <tr key={idx} className="border-b last:border-0">
                                      <td className="px-3 py-1.5">
                                        <Badge variant="secondary" className="text-[10px]">
                                          {track.track_type === 'audio' ? '🎤 音频' : '📹 视频'}
                                        </Badge>
                                      </td>
                                      <td className="px-3 py-1.5 text-muted-foreground">
                                        {track.direction === 'publish' ? '发布' : '订阅'}
                                      </td>
                                      <td className={cn(
                                        "px-3 py-1.5 font-mono",
                                        track.packet_loss_ratio > 0.05 ? 'text-red-600' :
                                        track.packet_loss_ratio > 0.02 ? 'text-amber-600' : 'text-emerald-600'
                                      )}>
                                        {(track.packet_loss_ratio * 100).toFixed(2)}%
                                      </td>
                                      <td className={cn(
                                        "px-3 py-1.5 font-mono",
                                        track.rtt_ms > 200 ? 'text-red-600' :
                                        track.rtt_ms > 100 ? 'text-amber-600' : ''
                                      )}>
                                        {track.rtt_ms.toFixed(1)}ms
                                      </td>
                                      <td className={cn(
                                        "px-3 py-1.5 font-mono",
                                        track.jitter_ms > 30 ? 'text-red-600' :
                                        track.jitter_ms > 15 ? 'text-amber-600' : ''
                                      )}>
                                        {track.jitter_ms.toFixed(1)}ms
                                      </td>
                                      <td className="px-3 py-1.5 font-mono">
                                        {track.bitrate_kbps.toFixed(0)} kbps
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {webrtcError && (
                <p className="text-xs text-amber-600 mt-2">⚠️ {webrtcError}</p>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">无活跃房间</p>
          )}
        </CardContent>
      </Card>

      {/* UDP Port Status Section */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Circle className="h-4 w-4 text-amber-500" />
            UDP 端口状态
            {udpPorts?.port_range && (
              <span className="text-xs font-normal text-muted-foreground">
                ({udpPorts.port_range.start}–{udpPorts.port_range.end})
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {udpError && !udpPorts?.ports?.length ? (
            <p className="text-sm text-red-600">{udpError}</p>
          ) : udpPorts?.ports ? (
            <>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {udpPorts.ports.map(port => (
                  <div
                    key={port.port}
                    className="flex flex-col rounded-lg border px-3 py-2 space-y-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-mono font-medium">{port.port}</span>
                      <div className="flex items-center gap-1.5">
                        <Circle
                          className={cn(
                            "h-2 w-2 fill-current",
                            port.bound ? 'text-emerald-500' : 'text-gray-300'
                          )}
                        />
                        <span className={cn(
                          "text-[10px]",
                          port.bound ? 'text-emerald-600' : 'text-muted-foreground'
                        )}>
                          {port.bound ? '已绑定' : '空闲'}
                        </span>
                      </div>
                    </div>
                    {port.bound && (
                      <>
                        <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                          <span>接收队列: {port.recv_queue}</span>
                          <span>发送队列: {port.send_queue}</span>
                        </div>
                        {(port.recv_packets != null || port.send_packets != null) && (
                          <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                            {port.recv_packets != null && <span>收包: {port.recv_packets.toLocaleString()}</span>}
                            {port.send_packets != null && <span>发包: {port.send_packets.toLocaleString()}</span>}
                          </div>
                        )}
                        {port.process && (
                          <div className="text-[10px] text-muted-foreground truncate" title={port.process}>
                            进程: {port.process}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
              {udpError && (
                <p className="text-xs text-amber-600 mt-3">⚠️ {udpError}</p>
              )}
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
