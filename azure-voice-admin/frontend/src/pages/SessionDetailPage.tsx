import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Clock, Hash, MessageSquare } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useApi } from '@/hooks/useApi'
import { MarkdownMessage } from '@/components/chat/MarkdownMessage'
import { MessageMeta } from '@/components/chat/MessageMeta'
import type { Session, LogEntry, Message } from '@/types'

const statusConfig: Record<string, { label: string; className: string }> = {
  connecting: { label: '连接中', className: 'bg-yellow-100 text-yellow-800 border-yellow-200' },
  connected: { label: '已连接', className: 'bg-blue-100 text-blue-800 border-blue-200' },
  active: { label: '进行中', className: 'bg-emerald-100 text-emerald-800 border-emerald-200' },
  completed: { label: '已完成', className: 'bg-green-100 text-green-800 border-green-200' },
  error: { label: '错误', className: 'bg-red-100 text-red-800 border-red-200' },
  cancelled: { label: '已取消', className: 'bg-gray-100 text-gray-800 border-gray-200' },
}

function formatDuration(startTime: string, endTime: string | null): string {
  if (!endTime) return '进行中'
  const start = new Date(startTime).getTime()
  const end = new Date(endTime).getTime()
  const diffMs = end - start
  if (diffMs < 0) return '—'
  const seconds = Math.floor(diffMs / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  if (hours > 0) {
    return `${hours}h ${minutes % 60}m ${seconds % 60}s`
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`
  }
  return `${seconds}s`
}

function formatDateTime(isoString: string): string {
  return new Date(isoString).toLocaleString('zh-CN')
}

export function SessionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: session, loading, error } = useApi<Session>(`/api/sessions/${id}`)
  const { data: logs } = useApi<LogEntry[]>(`/api/sessions/${id}/logs`)
  const { data: messages } = useApi<Message[]>(`/api/sessions/${id}/messages`)

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-muted-foreground">加载中...</p>
      </div>
    )
  }

  if (error || !session) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-destructive">
          {error ? `加载失败: ${error.message}` : '会话不存在'}
        </p>
      </div>
    )
  }

  const status = statusConfig[session.status] ?? {
    label: session.status,
    className: 'bg-gray-100 text-gray-800 border-gray-200',
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate('/history')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="text-2xl font-bold">会话详情</h1>
        <Badge className={status.className}>{status.label}</Badge>
      </div>

      {/* Metadata */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">实例</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-semibold">{session.instance_name}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              开始时间
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-semibold">{formatDateTime(session.start_time)}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              时长
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-semibold">
              {formatDuration(session.start_time, session.end_time)}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1">
              <Hash className="h-3.5 w-3.5" />
              Input Tokens
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-semibold">{session.input_tokens.toLocaleString()}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1">
              <Hash className="h-3.5 w-3.5" />
              Output Tokens
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-semibold">{session.output_tokens.toLocaleString()}</p>
          </CardContent>
        </Card>

        {session.room_name && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-1">
                <MessageSquare className="h-3.5 w-3.5" />
                房间名称
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-lg font-semibold font-mono text-sm">{session.room_name}</p>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Error Message */}
      {session.error_message && (
        <Card className="border-destructive">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-destructive">错误信息</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-destructive">{session.error_message}</p>
          </CardContent>
        </Card>
      )}

      {/* End Time */}
      {session.end_time && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">结束时间</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm">{formatDateTime(session.end_time)}</p>
          </CardContent>
        </Card>
      )}

      {/* Debug Logs */}
      <div>
        <h2 className="text-lg font-semibold mb-4">调试日志</h2>
        {logs && logs.length > 0 ? (
          <div className="border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">时间</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">方向</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">事件类型</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">载荷</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} className="border-b hover:bg-muted/30">
                    <td className="px-3 py-2 font-mono text-xs text-muted-foreground whitespace-nowrap">
                      {new Date(log.timestamp).toLocaleTimeString('zh-CN')}
                    </td>
                    <td className="px-3 py-2">
                      <Badge
                        className={
                          log.direction === 'inbound'
                            ? 'bg-blue-100 text-blue-700 border-blue-200'
                            : log.direction === 'outbound'
                              ? 'bg-green-100 text-green-700 border-green-200'
                              : 'bg-gray-100 text-gray-700 border-gray-200'
                        }
                      >
                        {log.direction}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{log.event_type}</td>
                    <td className="px-3 py-2 font-mono text-xs text-muted-foreground max-w-xs truncate">
                      {log.payload.length > 100
                        ? log.payload.substring(0, 100) + '...'
                        : log.payload}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="flex items-center justify-center p-8 border rounded-lg">
            <p className="text-muted-foreground">暂无调试日志</p>
          </div>
        )}
      </div>

      {/* Conversation Transcript */}
      <div>
        <h2 className="text-lg font-semibold mb-4">对话记录</h2>
        {messages && messages.length > 0 ? (
          <div className="space-y-3 border rounded-lg p-4 max-h-[600px] overflow-y-auto">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[75%] rounded-lg px-4 py-2 ${
                    msg.role === 'user'
                      ? 'bg-blue-500 text-white'
                      : 'bg-gray-100 text-gray-900'
                  }`}
                >
                  {msg.role === 'user' ? (
                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                  ) : (
                    <>
                      <MarkdownMessage content={msg.content} />
                      <MessageMeta model={msg.model} endpoint={msg.endpoint} />
                    </>
                  )}
                  <p
                    className={`text-xs mt-1 ${
                      msg.role === 'user' ? 'text-blue-100' : 'text-gray-400'
                    }`}
                  >
                    {msg.timestamp
                      ? new Date(msg.timestamp).toLocaleTimeString('zh-CN')
                      : ''}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex items-center justify-center p-8 border rounded-lg">
            <p className="text-muted-foreground">暂无对话记录</p>
          </div>
        )}
      </div>
    </div>
  )
}
