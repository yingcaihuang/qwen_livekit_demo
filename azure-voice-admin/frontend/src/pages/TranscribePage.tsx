import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { FileText, Mic, MicOff, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useLiveKit } from '@/hooks/useLiveKit'
import type { Instance } from '@/types'

const SOURCE_LANGUAGES = [
  { value: '', label: 'Auto-detect (自动检测)' },
  { value: 'en', label: 'English' },
  { value: 'zh', label: '中文 (Chinese)' },
  { value: 'ja', label: '日本語 (Japanese)' },
  { value: 'ko', label: '한국어 (Korean)' },
  { value: 'es', label: 'Español (Spanish)' },
  { value: 'fr', label: 'Français (French)' },
  { value: 'de', label: 'Deutsch (German)' },
  { value: 'pt', label: 'Português (Portuguese)' },
  { value: 'ru', label: 'Русский (Russian)' },
  { value: 'ar', label: 'العربية (Arabic)' },
  { value: 'hi', label: 'हिन्दी (Hindi)' },
  { value: 'it', label: 'Italiano (Italian)' },
]

export function TranscribePage() {
  const [searchParams] = useSearchParams()
  const instanceId = searchParams.get('instance') ?? ''

  const [instanceName, setInstanceName] = useState('')
  const [sourceLanguage, setSourceLanguage] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [livekitToken, setLivekitToken] = useState('')
  const [livekitUrl, setLivekitUrl] = useState('')
  const [isStarting, setIsStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [transcript, setTranscript] = useState<string[]>([])

  const { connectionState, connect, disconnect, isMicEnabled, toggleMic } = useLiveKit({
    token: livekitToken,
    url: livekitUrl,
    autoConnect: false,
  })

  // Fetch instance info
  useEffect(() => {
    if (!instanceId) return
    fetch(`/api/instances/${instanceId}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data: Instance | null) => {
        if (data) setInstanceName(data.name)
      })
      .catch(() => {})
  }, [instanceId])

  // Connect to LiveKit once we have token
  useEffect(() => {
    if (livekitToken && livekitUrl && connectionState === 'idle') {
      connect()
    }
  }, [livekitToken, livekitUrl, connectionState, connect])

  // WebSocket for real-time transcript
  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    const ws = new WebSocket(
      `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/sessions/${sessionId}/logs`
    )
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.event_type === 'message.added') {
          const payload = JSON.parse(data.payload || '{}')
          if (payload.text && !cancelled) {
            setTranscript((prev) => [...prev, payload.text])
          }
        }
      } catch {
        // ignore parse errors
      }
    }
    return () => {
      cancelled = true
      ws.close()
    }
  }, [sessionId])

  const handleStart = useCallback(async () => {
    if (!instanceId) {
      setError('未选择实例')
      return
    }
    setIsStarting(true)
    setError(null)
    setTranscript([])
    try {
      const res = await fetch('/api/transcribe-sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ instance_id: instanceId, source_language: sourceLanguage }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error(d.detail || `创建失败 (HTTP ${res.status})`)
      }
      const data = await res.json()
      setSessionId(data.session_id)
      setLivekitToken(data.livekit_token)
      setLivekitUrl(data.livekit_url)
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建转录会话失败')
    } finally {
      setIsStarting(false)
    }
  }, [instanceId, sourceLanguage])

  const handleStop = useCallback(async () => {
    if (sessionId) {
      await fetch(`/api/sessions/${sessionId}/stop`, { method: 'POST', credentials: 'include' }).catch(
        () => {}
      )
    }
    disconnect()
    setSessionId(null)
    setLivekitToken('')
    setLivekitUrl('')
  }, [sessionId, disconnect])

  const isActive = connectionState === 'connected'

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="bg-gradient-to-r from-rose-500 to-pink-500 bg-clip-text text-3xl font-bold tracking-tight text-transparent">
          实时转录 / Realtime Transcribe
        </h1>
        <p className="text-sm text-muted-foreground">
          {instanceName
            ? `实例：${instanceName}`
            : '基于 Azure GPT Realtime Whisper 的实时语音转录'}
        </p>
      </div>

      {!instanceId ? (
        <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 rounded-2xl border border-dashed p-10 text-center text-muted-foreground">
          <FileText className="h-10 w-10" />
          <p>未选择实例，请从实例列表选择一个转录实例后再进入。</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Controls */}
          <div className="flex flex-wrap items-center gap-4 rounded-2xl border bg-card p-4 shadow-sm">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">输入语言</label>
              <select
                value={sourceLanguage}
                onChange={(e) => setSourceLanguage(e.target.value)}
                disabled={isActive || isStarting}
                className="h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
              >
                {SOURCE_LANGUAGES.map((l) => (
                  <option key={l.value} value={l.value}>
                    {l.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="ml-auto flex items-center gap-2">
              {isActive && (
                <Button variant="outline" size="sm" onClick={toggleMic}>
                  {isMicEnabled ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
                </Button>
              )}
              {!isActive ? (
                <Button
                  onClick={handleStart}
                  disabled={isStarting}
                  className="bg-gradient-to-r from-rose-500 to-pink-500 text-white"
                >
                  {isStarting ? '连接中…' : '开始转录'}
                </Button>
              ) : (
                <Button variant="destructive" onClick={handleStop}>
                  <Square className="mr-1 h-4 w-4" /> 停止
                </Button>
              )}
            </div>
          </div>

          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          )}

          {/* Scrolling Transcript */}
          <div className="rounded-2xl border bg-card shadow-sm">
            <div className="border-b px-4 py-3">
              <h3 className="text-sm font-medium">转录文本</h3>
            </div>
            <div className="max-h-[60vh] overflow-y-auto p-4">
              {transcript.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  {isActive ? '正在等待语音输入…' : '点击「开始转录」后对着麦克风说话'}
                </p>
              ) : (
                <div className="space-y-1 font-mono text-sm leading-relaxed">
                  {transcript.map((line, idx) => (
                    <p key={idx}>{line}</p>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
