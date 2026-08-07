import { useState, useCallback } from 'react'
import type { KeyboardEvent } from 'react'
import { SendHorizonal, Plus, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { ChatParams } from '@/types'

interface ChatComposerProps {
  /** 是否有响应正在生成中（禁用输入与发送） */
  streaming: boolean
  /** 当前 Chat 参数（发送时透传给 sendMessage） */
  params: ChatParams
  /** 发送消息回调（追加用户消息并发起流式请求） */
  onSend: (content: string, params: ChatParams) => void
  /** 新对话回调（清空上下文，需求 2.7） */
  onNewConversation: () => void
}

/**
 * 底部输入区：多行文本框 + 发送按钮 + 新对话按钮。
 * - Enter 发送，Shift+Enter 换行
 * - 流式生成中禁用发送
 */
export function ChatComposer({
  streaming,
  params,
  onSend,
  onNewConversation,
}: ChatComposerProps) {
  const [value, setValue] = useState('')

  const submit = useCallback(() => {
    const content = value.trim()
    if (!content || streaming) return
    onSend(content, params)
    setValue('')
  }, [value, streaming, onSend, params])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        submit()
      }
    },
    [submit]
  )

  return (
    <div className="border-t bg-background/80 p-3 backdrop-blur">
      <div className="flex items-end gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onNewConversation}
          disabled={streaming}
          className="h-[44px] shrink-0"
          title="清空当前对话并开始新会话"
        >
          <Plus aria-hidden="true" />
          新对话
        </Button>
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={streaming}
          rows={1}
          placeholder={streaming ? '正在生成回复…' : '输入消息，Enter 发送，Shift+Enter 换行'}
          className="max-h-40 min-h-[44px] flex-1 resize-y rounded-lg border border-input bg-transparent px-3 py-2.5 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        />
        <Button
          type="button"
          onClick={submit}
          disabled={streaming || value.trim().length === 0}
          className="h-[44px] shrink-0 bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-sm transition hover:from-indigo-700 hover:to-violet-700"
        >
          {streaming ? (
            <Loader2 className="animate-spin" aria-hidden="true" />
          ) : (
            <SendHorizonal aria-hidden="true" />
          )}
          发送
        </Button>
      </div>
    </div>
  )
}
