import { Bot, User } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ChatMessage } from '@/types'
import { MarkdownMessage } from './MarkdownMessage'
import { MessageMeta } from './MessageMeta'

interface ChatBubbleProps {
  message: ChatMessage
  /** 该气泡是否为正在流式生成中的 assistant 消息 */
  isStreaming?: boolean
}

/** 三个跳动的圆点，表示 assistant 正在生成（内容为空时展示）。 */
function TypingIndicator() {
  return (
    <span className="flex items-center gap-1 py-1" aria-label="正在生成回复">
      <span className="h-2 w-2 animate-bounce rounded-full bg-indigo-400 [animation-delay:-0.3s]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-violet-400 [animation-delay:-0.15s]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-fuchsia-400" />
    </span>
  )
}

/**
 * 单条消息气泡。
 * - user：右侧，靛紫渐变、白字
 * - assistant：左侧，中性底色
 * - system（一般不出现在列表）：居中、弱化展示
 * assistant 内容为空且处于流式中时展示打字指示器（需求 2.2）。
 */
export function ChatBubble({ message, isStreaming = false }: ChatBubbleProps) {
  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'

  if (isSystem) {
    return (
      <div className="flex justify-center">
        <div className="max-w-[80%] rounded-lg bg-muted/60 px-3 py-1.5 text-center text-xs text-muted-foreground">
          {message.content}
        </div>
      </div>
    )
  }

  const showTyping = !isUser && isStreaming && message.content.length === 0

  return (
    <div className={cn('flex w-full gap-3', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-500 to-teal-500 text-white shadow-sm"
          aria-hidden="true"
        >
          <Bot className="h-4 w-4" />
        </div>
      )}
      {isUser ? (
        // user：右对齐紧凑气泡，靛紫渐变白字
        <div className="max-w-[75%] break-words whitespace-pre-wrap rounded-2xl rounded-br-sm bg-gradient-to-br from-indigo-600 to-violet-600 px-4 py-2.5 text-sm text-white shadow-sm">
          {message.content}
        </div>
      ) : (
        // assistant：占满会话列剩余宽度，富文本可用整宽（公式/图/表/图片有空间）
        <div className="min-w-0 flex-1 break-words rounded-2xl rounded-bl-sm border bg-card px-4 py-2.5 text-sm text-card-foreground shadow-sm">
          {showTyping ? (
            <TypingIndicator />
          ) : (
            <>
              <MarkdownMessage content={message.content} />
              <MessageMeta model={message.model} endpoint={message.endpoint} />
            </>
          )}
        </div>
      )}
      {isUser && (
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-sm"
          aria-hidden="true"
        >
          <User className="h-4 w-4" />
        </div>
      )}
    </div>
  )
}
