import { memo, useMemo, type ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeHighlight from 'rehype-highlight'
import { cn } from '@/lib/utils'
import { Mermaid } from './Mermaid'
import { ScrollablePane } from './ScrollablePane'

// 数学公式与代码高亮主题样式（整个应用只需在此处引入一次）。
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/github.css'

/**
 * 将模型输出中的 LaTeX 定界符归一化为 remark-math 识别的 `$` 定界符。
 *
 * - 显示公式 `\[ ... \]` -> 块级 `$$ ... $$`（前后加空行使其成为块）。
 * - 行内公式 `\( ... \)` -> 行内 `$ ... $`。
 * - 不触碰围栏代码块（```...```）与行内代码（`...`），避免误伤含方括号的代码。
 * - 使用函数形式的替换，保证替换串中的 `$` 按字面插入（规避 `$$` 特殊替换语义）。
 * - 已有的 `$...$` / `$$...$$` 不受影响（不会被二次转换）。
 * - 流式未闭合时（如只有 `\[`）仅产生未匹配的 `$$`，KaTeX/remark-math 会忽略或按文本显示，不会崩溃。
 */
export function normalizeMathDelimiters(src: string): string {
  // 切分出代码段（奇数下标）与非代码段（偶数下标），只转换非代码段。
  const parts = src.split(/(```[\s\S]*?```|`[^`]*`)/g)
  return parts
    .map((seg, i) => {
      if (i % 2 === 1) return seg // 代码段，原样保留
      return seg
        .replace(/\\\[/g, () => '\n\n$$\n')
        .replace(/\\\]/g, () => '\n$$\n\n')
        .replace(/\\\(/g, () => '$')
        .replace(/\\\)/g, () => '$')
    })
    .join('')
}

/** 把 react-markdown 传入的 children 拍平为纯字符串（用于代码块取源码）。 */
function childrenToString(children: ReactNode): string {
  if (children == null) return ''
  if (typeof children === 'string') return children
  if (typeof children === 'number') return String(children)
  if (Array.isArray(children)) return children.map(childrenToString).join('')
  if (
    typeof children === 'object' &&
    'props' in (children as { props?: { children?: ReactNode } }) &&
    (children as { props?: { children?: ReactNode } }).props
  ) {
    return childrenToString((children as { props: { children?: ReactNode } }).props.children)
  }
  return ''
}

// Tailwind v4 会重置列表/标题等默认样式，这里通过 components 覆盖补回可读的排版。
const components: Components = {
  p: ({ children }) => <p className="my-2 leading-relaxed first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  h1: ({ children }) => (
    <h1 className="mb-2 mt-4 text-xl font-semibold first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2 mt-4 text-lg font-semibold first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-1.5 mt-3 text-base font-semibold first:mt-0">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="mb-1.5 mt-3 text-sm font-semibold first:mt-0">{children}</h4>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-indigo-600 underline underline-offset-2 hover:text-indigo-500"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-4 border-border pl-3 text-muted-foreground italic">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-border" />,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-muted/60">{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => <tr className="border-b border-border">{children}</tr>,
  th: ({ children }) => (
    <th className="border border-border px-2 py-1 text-left font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="border border-border px-2 py-1 align-top">{children}</td>,
  // react-markdown 会用 <pre> 包裹块级代码；这里透传，块级样式由 code 渲染器负责，
  // 避免出现 <pre><pre> 嵌套。
  pre: ({ children }) => <>{children}</>,
  code: ({ className, children }) => {
    const match = /language-(\w+)/.exec(className ?? '')
    const codeString = childrenToString(children).replace(/\n$/, '')
    const isBlock = match != null || codeString.includes('\n')

    if (!isBlock) {
      return (
        <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">{children}</code>
      )
    }

    const lang = match?.[1]
    if (lang === 'mermaid') {
      // 图往往较大，用可平移容器承载（主用例）。
      return (
        <ScrollablePane>
          <Mermaid chart={codeString} />
        </ScrollablePane>
      )
    }

    // 宽代码块用可平移容器承载，保留高亮类。
    return (
      <ScrollablePane>
        <pre className="rounded-lg bg-zinc-900 px-4 py-3 text-[0.85em] leading-relaxed">
          <code className={cn('hljs font-mono', className)}>{children}</code>
        </pre>
      </ScrollablePane>
    )
  },
  // 图片以自然尺寸渲染并置于可平移容器内，超出部分可上下左右拖动查看。
  img: ({ src, alt }) => {
    if (typeof src !== 'string' || src.length === 0) return null
    return (
      <ScrollablePane>
        <img src={src} alt={alt ?? ''} className="max-w-none rounded-lg" />
      </ScrollablePane>
    )
  },
}

interface MarkdownMessageProps {
  content: string
}

/**
 * 富文本 Markdown 渲染组件（用于展示模型输出）。
 *
 * - GFM（表格/任务列表/删除线/自动链接）、数学公式（KaTeX）、代码高亮。
 * - 不启用 raw HTML（保留默认净化），因为内容来自模型，避免 XSS。
 * - ```mermaid 代码块渲染为图；流式未完成时回退为原始源码，不崩溃。
 */
function MarkdownMessageImpl({ content }: MarkdownMessageProps) {
  const normalized = useMemo(() => normalizeMathDelimiters(content), [content])
  return (
    <div className="markdown-body w-full min-w-0 text-sm">
      {/* 块级公式（rehype-katex 输出 .katex-display）过宽时允许横向滚动。 */}
      <style>{'.markdown-body .katex-display{overflow-x:auto;overflow-y:hidden}'}</style>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex, rehypeHighlight]}
        components={components}
      >
        {normalized}
      </ReactMarkdown>
    </div>
  )
}

export const MarkdownMessage = memo(MarkdownMessageImpl)
