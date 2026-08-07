import { ArrowDown, ArrowUp } from 'lucide-react'
import type { ImageGeneration } from '@/types'

interface ImageResultGridProps {
  result: ImageGeneration
}

/**
 * 结果网格：以响应式网格渲染 result.images 中的每个变体 URL；
 * 若存在用量则展示输入/输出 tokens（需求 4.5）。
 */
export function ImageResultGrid({ result }: ImageResultGridProps) {
  const images = result.images ?? []
  const hasUsage =
    (result.input_tokens ?? 0) > 0 || (result.output_tokens ?? 0) > 0

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {images.length} 张变体
          {result.has_reference && ' · 基于参考图编辑'}
        </p>
        {hasUsage && (
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <ArrowUp className="h-3 w-3 text-violet-500" />
              {result.input_tokens} in
            </span>
            <span className="inline-flex items-center gap-1">
              <ArrowDown className="h-3 w-3 text-amber-500" />
              {result.output_tokens} out
            </span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {images.map((url, index) => (
          <a
            key={url}
            href={url}
            target="_blank"
            rel="noreferrer"
            className="group overflow-hidden rounded-xl border bg-card shadow-sm transition hover:shadow-md"
          >
            <img
              src={url}
              alt={`生成图片 ${index + 1}`}
              className="aspect-square w-full object-cover transition group-hover:scale-[1.02]"
              loading="lazy"
            />
          </a>
        ))}
      </div>
    </div>
  )
}
