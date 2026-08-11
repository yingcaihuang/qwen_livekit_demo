import { useEffect, useState, useCallback } from 'react'
import { Activity, Wifi, WifiOff, Server, Globe, RefreshCw, Circle, Zap } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface MonitorData {
  livekit: { reachable: boolean; url: string }
  active_sessions: number
  active_workers: string[]
  ports: { label: string; host: string; port: number; protocol: string; reachable: boolean }[]
  environment: { node_ip: string; public_url: string; livekit_url: string }
  recent_sessions: {
    id: string; room_name: string; status: string; start_time: string
    end_time: string | null; input_tokens: number; output_tokens: number
    instance_name: string; type: string; duration_seconds: number | null
  }[]
}

interface RoomData {
  rooms: { name: string; sid: string; num_participants: number; num_publishers: number; creation_time: number }[]
  error?: string
}

interface NetworkTest {
  tests: { test: string; status: string; result: string; latency_ms: number | null }[]
  timestamp: number
}

export function MonitorPage() {
  const [data, setData] = useState<MonitorData | null>(null)
  const [rooms, setRooms] = useState<RoomData | null>(null)
  const [network, setNetwork] = useState<NetworkTest | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchAll = useCallback(async () => {
    setRefreshing(true)
    try {
      const [overviewRes, roomsRes, networkRes] = await Promise.all([
        fetch('/api/admin/monitor/overview', { credentials: 'include' }),
        fetch('/api/admin/monitor/rooms', { credentials: 'include' }),
        fetch('/api/admin/monitor/network-test', { credentials: 'include' }),
      ])
      if (overviewRes.ok) setData(await overviewRes.json())
      if (roomsRes.ok) setRooms(await roomsRes.json())
      if (networkRes.ok) setNetwork(await networkRes.json())
    } catch {
      // silently ignore fetch errors
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

  if (loading) {
    return <div className="flex items-center justify-center p-12"><p className="text-muted-foreground">加载中...</p></div>
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="bg-gradient-to-r from-indigo-600 to-violet-500 bg-clip-text text-3xl font-bold tracking-tight text-transparent">
            系统监控
          </h1>
          <p className="text-sm text-muted-foreground">LiveKit 连接状态、网络链路和活跃会话监控</p>
        </div>
        <Button variant="outline" onClick={fetchAll} disabled={refreshing}>
          <RefreshCw className={cn("h-4 w-4", refreshing && "animate-spin")} />
          {refreshing ? '刷新中' : '刷新'}
        </Button>
      </div>

      {/* Status Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="flex items-center gap-3 py-4">
            {data?.livekit.reachable ? <Wifi className="h-8 w-8 text-emerald-500" /> : <WifiOff className="h-8 w-8 text-red-500" />}
            <div>
              <p className="text-sm font-medium">LiveKit</p>
              <p className={cn("text-xs", data?.livekit.reachable ? "text-emerald-600" : "text-red-600")}>
                {data?.livekit.reachable ? '已连接' : '不可达'}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 py-4">
            <Activity className="h-8 w-8 text-blue-500" />
            <div>
              <p className="text-sm font-medium">活跃会话</p>
              <p className="text-2xl font-bold">{data?.active_sessions ?? 0}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 py-4">
            <Zap className="h-8 w-8 text-amber-500" />
            <div>
              <p className="text-sm font-medium">Worker 进程</p>
              <p className="text-2xl font-bold">{data?.active_workers.length ?? 0}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 py-4">
            <Globe className="h-8 w-8 text-violet-500" />
            <div>
              <p className="text-sm font-medium">Node IP</p>
              <p className="text-xs font-mono">{data?.environment.node_ip || '-'}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Active Rooms */}
      <Card>
        <CardHeader><CardTitle className="text-base flex items-center gap-2"><Server className="h-4 w-4 text-indigo-500" />活跃房间</CardTitle></CardHeader>
        <CardContent>
          {rooms?.rooms && rooms.rooms.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/50">
                  <tr>
                    <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">房间名</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">参与者</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">发布者</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {rooms.rooms.map(room => (
                    <tr key={room.sid} className="border-b last:border-0">
                      <td className="px-4 py-2 font-mono text-xs">{room.name}</td>
                      <td className="px-4 py-2"><Badge variant="secondary">{room.num_participants}</Badge></td>
                      <td className="px-4 py-2"><Badge variant="secondary">{room.num_publishers}</Badge></td>
                      <td className="px-4 py-2 text-xs text-muted-foreground">{new Date(room.creation_time * 1000).toLocaleString('zh-CN')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{rooms?.error || '当前无活跃房间'}</p>
          )}
        </CardContent>
      </Card>

      {/* Network Tests */}
      <Card>
        <CardHeader><CardTitle className="text-base flex items-center gap-2"><Globe className="h-4 w-4 text-cyan-500" />网络链路测试</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-2">
            {network?.tests.map((test, i) => (
              <div key={i} className="flex items-center justify-between rounded-lg border px-4 py-2">
                <div className="flex items-center gap-2">
                  <Circle className={cn("h-2.5 w-2.5 fill-current", test.status === 'ok' ? 'text-emerald-500' : 'text-red-500')} />
                  <span className="text-sm">{test.test}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono text-muted-foreground">{test.result}</span>
                  {test.latency_ms != null && (
                    <Badge variant="outline" className="text-xs">{test.latency_ms}ms</Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Port Status */}
      <Card>
        <CardHeader><CardTitle className="text-base flex items-center gap-2"><Server className="h-4 w-4 text-amber-500" />端口状态</CardTitle></CardHeader>
        <CardContent>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {data?.ports.map((p, i) => (
              <div key={i} className="flex items-center justify-between rounded-lg border px-3 py-2">
                <span className="text-sm">{p.label}</span>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-muted-foreground">{p.port}/{p.protocol}</span>
                  <Circle className={cn("h-2 w-2 fill-current", p.reachable ? 'text-emerald-500' : 'text-red-500')} />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Recent Sessions */}
      <Card>
        <CardHeader><CardTitle className="text-base flex items-center gap-2"><Activity className="h-4 w-4 text-blue-500" />最近会话</CardTitle></CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">房间</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">实例</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">类型</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">状态</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">时长</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">Tokens</th>
                </tr>
              </thead>
              <tbody>
                {data?.recent_sessions.map(s => (
                  <tr key={s.id} className="border-b last:border-0 hover:bg-muted/30">
                    <td className="px-4 py-2 font-mono text-xs">{s.room_name || '-'}</td>
                    <td className="px-4 py-2 text-xs">{s.instance_name || '-'}</td>
                    <td className="px-4 py-2 text-xs">{s.type || '-'}</td>
                    <td className="px-4 py-2">
                      <Badge variant="outline" className="text-[10px]">{s.status}</Badge>
                    </td>
                    <td className="px-4 py-2 text-xs">{s.duration_seconds != null ? `${s.duration_seconds}s` : '-'}</td>
                    <td className="px-4 py-2 text-xs">{(s.input_tokens + s.output_tokens).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Environment */}
      <Card>
        <CardHeader><CardTitle className="text-base">环境配置</CardTitle></CardHeader>
        <CardContent>
          <div className="grid gap-2 sm:grid-cols-3 font-mono text-xs">
            <div className="rounded border p-2"><span className="text-muted-foreground">LIVEKIT_URL:</span> {data?.environment.livekit_url}</div>
            <div className="rounded border p-2"><span className="text-muted-foreground">PUBLIC_URL:</span> {data?.environment.public_url}</div>
            <div className="rounded border p-2"><span className="text-muted-foreground">NODE_IP:</span> {data?.environment.node_ip}</div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
