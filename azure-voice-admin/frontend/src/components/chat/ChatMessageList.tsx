import { useEffect, useRef } from 'react'
import { MessagesSquare } from 'lucide-react'
import { ChatBubble } from './ChatBubble'
import type { ChatMessage } from '@/types'

interface ChatMessageListProps {
  messages: ChatMessage[]
  /** 是否有响应正在生成中（用于最后一条 assistant 气泡的打字指示器） */
  streaming: boolean
}

/**
 * 多轮气泡列表：渲染完整对话并在内容变化时自动滚动到底部。
 * 空对话时展示引导空态。
 */
export function ChatMessageList({ messages, streaming }: ChatMessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // 新消息或流式增量时滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, streaming])

  if (messages.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-muted-foreground">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-500 text-white shadow-md">
          <MessagesSquare className="h-7 w-7" aria-hidden="true" />
        </div>
        <div className="space-y-1">
          <p className="text-sm font-medium text-foreground">开始一段新对话</p>
          <p className="text-xs">在下方输入消息，与所选实例进行多轮对话测试</p>
        </div>
      </div>
    )
  }

  const lastIndex = messages.length - 1

  return (
    <div className="space-y-4">
      {messages.map((message, index) => (
        <ChatBubble
          key={index}
          message={message}
          isStreaming={streaming && index === lastIndex && message.role === 'assistant'}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
