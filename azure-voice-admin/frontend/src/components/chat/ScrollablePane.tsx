import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react'
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ScrollablePaneProps {
  children: ReactNode
  /** 滚动容器最大高度（超出后可上下平移）。默认 70vh。 */
  maxHeight?: string
  /** 每次点击箭头滚动的步进（px）。 */
  step?: number
  /** 附加到最外层容器的类名。 */
  className?: string
}

/** 四个方向的可滚动状态。 */
interface ScrollState {
  up: boolean
  down: boolean
  left: boolean
  right: boolean
}

const INITIAL_STATE: ScrollState = { up: false, down: false, left: false, right: false }

/**
 * 可平移的滚动容器：内容超出时在上/下/左/右边缘浮出圆形箭头按钮，
 * 点击按对应方向平滑滚动。仅在该方向可继续滚动时才显示对应按钮。
 *
 * - 通过 ResizeObserver（内容尺寸变化）+ scroll 监听实时重算箭头可见性。
 * - 对 SSR/未挂载的 ref 做了防御，卸载时清理监听与 observer。
 * - 箭头带 aria-label 且可键盘聚焦；不拦截内容区域的指针事件。
 */
export function ScrollablePane({
  children,
  maxHeight = '70vh',
  step = 150,
  className,
}: ScrollablePaneProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<ScrollState>(INITIAL_STATE)

  const recompute = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const { scrollTop, scrollLeft, scrollHeight, scrollWidth, clientHeight, clientWidth } = el
    // 容差 1px，避免亚像素误差导致箭头闪烁。
    const tol = 1
    setState({
      up: scrollTop > tol,
      down: scrollTop + clientHeight < scrollHeight - tol,
      left: scrollLeft > tol,
      right: scrollLeft + clientWidth < scrollWidth - tol,
    })
  }, [])

  useEffect(() => {
    // 防御 SSR / 无 ResizeObserver 环境。
    if (typeof window === 'undefined') return
    const el = scrollRef.current
    if (!el) return

    recompute()

    el.addEventListener('scroll', recompute, { passive: true })

    let observer: ResizeObserver | undefined
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => recompute())
      observer.observe(el)
      if (contentRef.current) observer.observe(contentRef.current)
    }

    return () => {
      el.removeEventListener('scroll', recompute)
      observer?.disconnect()
    }
  }, [recompute])

  const scroll = useCallback(
    (dx: number, dy: number) => {
      scrollRef.current?.scrollBy({ left: dx, top: dy, behavior: 'smooth' })
    },
    []
  )

  const scrollStyle: CSSProperties = { maxHeight }

  const arrowBase =
    'absolute z-10 flex h-7 w-7 items-center justify-center rounded-full border ' +
    'border-border bg-background/80 text-muted-foreground shadow-sm backdrop-blur ' +
    'opacity-0 transition-opacity hover:bg-background hover:text-foreground ' +
    'group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none ' +
    'focus-visible:ring-2 focus-visible:ring-ring'

  return (
    <div className={cn('group relative my-3', className)}>
      <div ref={scrollRef} className="overflow-auto" style={scrollStyle}>
        <div ref={contentRef} className="w-max min-w-full">
          {children}
        </div>
      </div>

      {state.up && (
        <button
          type="button"
          aria-label="向上滚动"
          onClick={() => scroll(0, -step)}
          className={cn(arrowBase, 'left-1/2 top-1 -translate-x-1/2')}
        >
          <ChevronUp className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
      {state.down && (
        <button
          type="button"
          aria-label="向下滚动"
          onClick={() => scroll(0, step)}
          className={cn(arrowBase, 'bottom-1 left-1/2 -translate-x-1/2')}
        >
          <ChevronDown className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
      {state.left && (
        <button
          type="button"
          aria-label="向左滚动"
          onClick={() => scroll(-step, 0)}
          className={cn(arrowBase, 'left-1 top-1/2 -translate-y-1/2')}
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
      {state.right && (
        <button
          type="button"
          aria-label="向右滚动"
          onClick={() => scroll(step, 0)}
          className={cn(arrowBase, 'right-1 top-1/2 -translate-y-1/2')}
        >
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
    </div>
  )
}
