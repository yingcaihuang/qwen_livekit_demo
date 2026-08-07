import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertTriangle, MessageSquareText, Boxes } from 'lucide-react'
import { ChatMessageList } from '@/components/chat/ChatMessageList'
import { ChatComposer } from '@/components/chat/ChatComposer'
import { ChatParamsPanel } from '@/components/chat/ChatParamsPanel'
import { useChatStream } from '@/hooks/useChatStream'
import { useApi } from '@/hooks/useApi'
import type { ChatParams, InstanceDetail } from '@/types'

const DEFAULT_PARAMS: ChatParams = {
  system_prompt: '',
  temperature: 1,
  max_tokens: null,
}

export function ChatPlaygroundPage() {
  const [searchParams] = useSearchParams()
  const instanceId = searchParams.get('instance') ?? ''

  return instanceId ? (
    <ChatPlayground instanceId={instanceId} />
  ) : (
    <MissingInstance />
  )
}

/** 缺少 instance 查询参数时的友好提示。 */
function MissingInstance() {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-3 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-500 to-orange-500 text-white shadow-md">
        <AlertTriangle className="h-7 w-7" aria-hidden="true" />
      </div>
      <div className="space-y-1">
        <h1 className="text-lg font-semibold">未选择实例</h1>
        <p className="text-sm text-muted-foreground">
          请从「实例管理」页面选择一个对话（chat）实例并点击「开始对话」。
        </p>
      </div>
    </div>
  )
}

interface ChatPlaygroundProps {
  instanceId: string
}

function ChatPlayground({ instanceId }: ChatPlaygroundProps) {
  const [params, setParams] = useState<ChatParams>(DEFAULT_PARAMS)
  const { data: instance } = useApi<InstanceDetail>(`/api/instances/${instanceId}`)
  const { messages, streaming, usage, error, sendMessage, newConversation } =
    useChatStream(instanceId)

  return (
    <div className="flex min-h-[calc(100vh-3rem)] flex-col gap-4 lg:h-[calc(100vh-3rem)]">
      {/* Header */}
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h1 className="flex items-center gap-2 bg-gradient-to-r from-emerald-600 to-teal-500 bg-clip-text text-2xl font-bold tracking-tight text-transparent">
            <MessageSquareText className="h-6 w-6 text-emerald-600" aria-hidden="true" />
            对话测试 / Chat Playground
          </h1>
          <p className="text-sm text-muted-foreground">多轮流式对话，实时逐字渲染模型回复</p>
        </div>
        {instance && (
          <div className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2 shadow-sm">
            <div
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-500 to-teal-500 text-white shadow-sm"
              aria-hidden="true"
            >
              <Boxes className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold" title={instance.name}>
                {instance.name}
              </div>
              <div className="truncate font-mono text-xs text-muted-foreground">
                {instance.deployment}
              </div>
            </div>
          </div>
        )}
      </header>

      {/* Error banner (需求 9.2，不崩溃当前视图) */}
      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <div>
            <span className="font-medium">请求出错：</span>
            {error}
          </div>
        </div>
      )}

      {/* Main: message column + params panel */}
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
        {/* Conversation */}
        <div className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-card shadow-sm">
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            <ChatMessageList messages={messages} streaming={streaming} />
          </div>
          <ChatComposer
            streaming={streaming}
            params={params}
            onSend={sendMessage}
            onNewConversation={newConversation}
          />
        </div>

        {/* Params panel */}
        <aside className="min-h-0 rounded-xl border bg-card shadow-sm">
          <ChatParamsPanel params={params} onChange={setParams} usage={usage} />
        </aside>
      </div>
    </div>
  )
}
