import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  ChatMessage,
  ChatParams,
  ChatStreamEvent,
  ChatTiming,
  TokenUsage,
} from '@/types'

/** useChatStream 暴露的状态与操作 */
export interface UseChatStreamResult {
  /** 完整对话（user + assistant），流式 assistant 消息随 delta 增量更新 */
  messages: ChatMessage[]
  /** 是否有响应正在生成中 */
  streaming: boolean
  /** 最近一次 done 事件返回的用量 */
  usage: TokenUsage | null
  /** 最近一次 done 事件返回的性能计时（可能为 null） */
  timing: ChatTiming | null
  /** 由 session 事件设置，跨轮次保留并在后续发送时复用 */
  sessionId: string | null
  /** error 事件或网络失败时设置（需求 9.2，不崩溃） */
  error: string | null
  /**
   * 追加用户消息并向 /api/chat/completions 发起 POST 流式请求。
   * @param content 用户输入文本
   * @param params  Chat 参数（system_prompt / temperature / max_tokens）
   */
  sendMessage: (content: string, params: ChatParams) => Promise<void>
  /** 清空上下文，开启新的 Chat_Session（需求 2.7） */
  newConversation: () => void
  /**
   * 载入已有会话以继续对话：复用给定 session_id 并预填历史消息。
   * 后续 sendMessage 会以该 session_id 追加到同一后端会话。
   * @param sessionId       要续聊的会话 ID
   * @param initialMessages 该会话的历史消息（user/assistant）
   */
  loadSession: (sessionId: string, initialMessages: ChatMessage[]) => void
}

const CHAT_ENDPOINT = '/api/chat/completions'

/**
 * 消费 Chat SSE 流的自定义 Hook。
 *
 * 由于端点是 POST（EventSource 仅支持 GET），采用 fetch + ReadableStream +
 * TextDecoder 手动解析 `data: {json}\n\n` 帧，并将 ChatStreamEvent 分发到状态。
 *
 * @param instanceId 目标 chat 实例 ID，作为请求体 instance_id 发送
 */
export function useChatStream(instanceId: string): UseChatStreamResult {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streaming, setStreaming] = useState(false)
  const [usage, setUsage] = useState<TokenUsage | null>(null)
  const [timing, setTiming] = useState<ChatTiming | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // 追踪最新的 messages / sessionId，避免 sendMessage 闭包捕获陈旧值
  const messagesRef = useRef<ChatMessage[]>([])
  const sessionIdRef = useRef<string | null>(null)
  // 当前进行中的请求控制器，用于卸载时取消
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  useEffect(() => {
    sessionIdRef.current = sessionId
  }, [sessionId])

  const newConversation = useCallback(() => {
    // 取消进行中的请求（若有）
    abortRef.current?.abort()
    abortRef.current = null
    setMessages([])
    setSessionId(null)
    setUsage(null)
    setTiming(null)
    setError(null)
    setStreaming(false)
  }, [])

  const loadSession = useCallback(
    (resumeSessionId: string, initialMessages: ChatMessage[]) => {
      // 取消进行中的请求（若有）
      abortRef.current?.abort()
      abortRef.current = null
      // 复用会话 ID，并同步 ref 以便 sendMessage 立即读取到最新值
      sessionIdRef.current = resumeSessionId
      setSessionId(resumeSessionId)
      messagesRef.current = initialMessages
      setMessages(initialMessages)
      setUsage(null)
      setTiming(null)
      setError(null)
      setStreaming(false)
    },
    [],
  )

  const sendMessage = useCallback(
    async (content: string, params: ChatParams) => {
      // 已有请求进行中则忽略新的发送
      if (abortRef.current) return

      const userMessage: ChatMessage = { role: 'user', content }
      // 累积历史（不含 system，system_prompt 由后端注入首条 system 消息）
      const outgoing = [...messagesRef.current, userMessage]

      // 追加用户消息与一个空的 assistant 占位气泡，供 delta 增量填充
      setMessages([...outgoing, { role: 'assistant', content: '' }])
      setStreaming(true)
      setError(null)
      setUsage(null)
      setTiming(null)

      const controller = new AbortController()
      abortRef.current = controller

      // 将 delta 内容追加到最后一条（assistant 占位）消息
      const appendDelta = (delta: string) => {
        setMessages((prev) => {
          if (prev.length === 0) return prev
          const next = prev.slice()
          const last = next[next.length - 1]
          if (!last || last.role !== 'assistant') return prev
          next[next.length - 1] = { ...last, content: last.content + delta }
          return next
        })
      }

      const handleEvent = (event: ChatStreamEvent) => {
        switch (event.type) {
          case 'session':
            setSessionId(event.session_id)
            break
          case 'delta':
            appendDelta(event.content)
            break
          case 'done':
            setUsage(event.usage)
            if (event.timing) setTiming(event.timing)
            break
          case 'error':
            setError(event.message)
            break
        }
      }

      // 解析单个 SSE 帧（可能跨多行，取 data: 行）
      const parseFrame = (frame: string) => {
        const dataLines: string[] = []
        for (const rawLine of frame.split('\n')) {
          const line = rawLine.replace(/\r$/, '')
          if (line.startsWith('data:')) {
            dataLines.push(line.slice(5).trimStart())
          }
        }
        if (dataLines.length === 0) return
        const payload = dataLines.join('\n')
        if (!payload || payload === '[DONE]') return
        try {
          handleEvent(JSON.parse(payload) as ChatStreamEvent)
        } catch {
          // 忽略无法解析的帧（容忍非 JSON 的心跳/注释）
        }
      }

      try {
        const response = await fetch(CHAT_ENDPOINT, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            instance_id: instanceId,
            session_id: sessionIdRef.current ?? undefined,
            messages: outgoing,
            system_prompt: params.system_prompt,
            temperature: params.temperature,
            max_tokens: params.max_tokens,
          }),
          signal: controller.signal,
        })

        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        // 逐块读取，缓冲部分行，按双换行分帧（容忍跨块拆分）
        for (;;) {
          const { value, done } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          let sepIndex: number
          // SSE 帧以空行（\n\n）分隔
          while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
            const frame = buffer.slice(0, sepIndex)
            buffer = buffer.slice(sepIndex + 2)
            parseFrame(frame)
          }
        }

        // 冲刷解码器并处理残留缓冲
        buffer += decoder.decode()
        if (buffer.trim().length > 0) {
          parseFrame(buffer)
        }
      } catch (err) {
        // AbortError 属于主动取消（卸载 / 新对话），不视为错误
        if (!(err instanceof DOMException && err.name === 'AbortError')) {
          setError(err instanceof Error ? err.message : String(err))
        }
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null
        }
        setStreaming(false)
      }
    },
    [instanceId],
  )

  // 卸载时取消进行中的请求
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      abortRef.current = null
    }
  }, [])

  return {
    messages,
    streaming,
    usage,
    timing,
    sessionId,
    error,
    sendMessage,
    newConversation,
    loadSession,
  }
}
