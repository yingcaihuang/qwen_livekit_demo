import { useEffect, useId, useRef, useState } from 'react'
import mermaid from 'mermaid'

// 模块加载时初始化一次。securityLevel: 'strict' 会对图中文本做转义，避免注入。
mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'default' })

interface MermaidProps {
  /** mermaid 图定义源码（来自模型输出的 ```mermaid 代码块） */
  chart: string
}

/**
 * 渲染一个 mermaid 图。
 *
 * 关键点：流式输出过程中 ```mermaid 代码块往往是不完整/非法的，
 * mermaid.render 会抛错。此时回退为展示原始源码（<pre>），不崩溃；
 * 待代码块完整后再成功渲染为 SVG。
 */
export function Mermaid({ chart }: MermaidProps) {
  const rawId = useId()
  // useId 生成的 id 含有 ":"，不是合法的 DOM/CSS 选择器，做一次清洗。
  const domId = `mermaid-${rawId.replace(/[^a-zA-Z0-9_-]/g, '')}`
  const [svg, setSvg] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const source = chart.trim()

    if (!source) {
      setSvg(null)
      setFailed(false)
      return
    }

    mermaid
      .render(domId, source)
      .then(({ svg: rendered }) => {
        if (!cancelled && mountedRef.current) {
          setSvg(rendered)
          setFailed(false)
        }
      })
      .catch(() => {
        // 常见于流式过程中图未完整；回退为原始源码。
        if (!cancelled && mountedRef.current) {
          setSvg(null)
          setFailed(true)
        }
      })

    return () => {
      cancelled = true
    }
  }, [chart, domId])

  if (svg) {
    return (
      <div
        className="flex justify-center"
        // 该 SVG 由 mermaid 从图源码生成（securityLevel: 'strict'），可安全注入。
        // 横/纵向滚动由外层 ScrollablePane 统一处理。
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    )
  }

  // 尚未渲染成功（或渲染失败）时回退展示原始源码。
  return (
    <pre
      className={
        'rounded-lg bg-zinc-900 px-4 py-3 text-[0.85em] leading-relaxed text-zinc-100' +
        (failed ? ' opacity-90' : '')
      }
    >
      <code className="font-mono">{chart}</code>
    </pre>
  )
}
