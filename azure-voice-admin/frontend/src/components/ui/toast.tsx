import { useEffect, useState } from 'react'
import { Bell, X } from 'lucide-react'
import { cn } from '@/lib/utils'

/** 单条 toast 的动作按钮（可选）。 */
export interface ToastAction {
  label: string
  onClick: () => void
}

/** 调用 toast() 时传入的选项。 */
export interface ToastOptions {
  title: string
  description?: string
  action?: ToastAction
  /** 自动消失时长（毫秒），默认 4000；传入 0 或负数则不自动消失。 */
  duration?: number
}

/** 内部完整的 toast 数据（含唯一 id）。 */
interface ToastItem extends ToastOptions {
  id: number
}

type Listener = (toasts: ToastItem[]) => void

const DEFAULT_DURATION = 4000

/**
 * 模块级 toast 存储：基于订阅（subscribe）的极简事件发射器。
 * 组件之外的任意位置都可以调用 `toast()` 推送通知，`<Toaster/>` 订阅并渲染。
 */
class ToastStore {
  private toasts: ToastItem[] = []
  private listeners = new Set<Listener>()
  private nextId = 1

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener)
    listener(this.toasts)
    return () => {
      this.listeners.delete(listener)
    }
  }

  private emit(): void {
    for (const listener of this.listeners) listener(this.toasts)
  }

  add(options: ToastOptions): number {
    const id = this.nextId++
    this.toasts = [...this.toasts, { ...options, id }]
    this.emit()
    return id
  }

  dismiss(id: number): void {
    this.toasts = this.toasts.filter((t) => t.id !== id)
    this.emit()
  }
}

const store = new ToastStore()

/**
 * 推送一条 toast 通知。可在任意位置（含组件之外）调用。
 * 返回该 toast 的 id，可用于手动关闭。
 */
export function toast(options: ToastOptions): number {
  return store.add(options)
}

/** 手动关闭指定 toast。 */
export function dismissToast(id: number): void {
  store.dismiss(id)
}

/** 单条 toast 卡片：负责挂载动画与自动消失定时器。 */
function ToastCard({ item }: { item: ToastItem }) {
  // 挂载后触发进入动画（从右侧滑入 + 淡入）
  const [entered, setEntered] = useState(false)

  useEffect(() => {
    const raf = requestAnimationFrame(() => setEntered(true))
    return () => cancelAnimationFrame(raf)
  }, [])

  useEffect(() => {
    const duration = item.duration ?? DEFAULT_DURATION
    if (duration <= 0) return
    const timer = setTimeout(() => store.dismiss(item.id), duration)
    return () => clearTimeout(timer)
  }, [item.id, item.duration])

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'pointer-events-auto flex w-80 items-start gap-3 rounded-2xl border border-white/40 bg-gradient-to-br from-amber-50 via-white to-orange-50 p-4 shadow-xl ring-1 ring-black/5 backdrop-blur transition-all duration-300 ease-out',
        entered ? 'translate-x-0 opacity-100' : 'translate-x-8 opacity-0',
      )}
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500 to-orange-500 text-white shadow-md">
        <Bell className="h-5 w-5" aria-hidden="true" />
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-sm font-semibold leading-snug text-foreground">{item.title}</p>
        {item.description && (
          <p className="text-xs leading-relaxed text-muted-foreground">{item.description}</p>
        )}
        {item.action && (
          <button
            type="button"
            onClick={() => {
              item.action?.onClick()
              store.dismiss(item.id)
            }}
            className="mt-1 inline-flex items-center rounded-lg bg-gradient-to-r from-amber-500 to-orange-500 px-3 py-1 text-xs font-semibold text-white shadow-sm transition-opacity hover:opacity-90"
          >
            {item.action.label}
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={() => store.dismiss(item.id)}
        aria-label="关闭通知"
        className="-mr-1 -mt-1 shrink-0 rounded-lg p-1 text-muted-foreground transition-colors hover:bg-black/5 hover:text-foreground"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  )
}

/**
 * Toaster：固定在右下角、纵向堆叠的 toast 容器。
 * 在应用根部挂载一次即可，任何位置调用 `toast()` 都会在此渲染。
 */
export function Toaster() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  useEffect(() => store.subscribe(setToasts), [])

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex flex-col gap-3">
      {toasts.map((item) => (
        <ToastCard key={item.id} item={item} />
      ))}
    </div>
  )
}
