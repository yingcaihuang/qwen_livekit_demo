import { useRef } from 'react'
import { Paperclip, Sparkles, X, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { ImageParams } from '@/types'

/** 可选的图像尺寸（Azure gpt-image 支持的常见取值） */
const SIZE_OPTIONS = [
  { value: '1024x1024', label: '1024 x 1024' },
  { value: '1536x1024', label: '1536 x 1024' },
  { value: '1024x1536', label: '1024 x 1536' },
  { value: 'auto', label: 'Auto' },
] as const

/** 质量选项：Low / Medium / High（需求 4.1） */
const QUALITY_OPTIONS: ReadonlyArray<{ value: ImageParams['quality']; label: string }> = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
]

interface ImagePromptBarProps {
  prompt: string
  onPromptChange: (value: string) => void
  size: string
  quality: ImageParams['quality']
  onSizeChange: (value: string) => void
  onQualityChange: (value: ImageParams['quality']) => void
  referenceImage: File | null
  onAttachReference: (file: File | null) => void
  onSubmit: () => void
  loading: boolean
}

const selectClass =
  'h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50'

/**
 * 图像提示词输入栏：prompt 文本框 + 内联 size/quality 选择 +
 * 附参考图按钮（附件后展示缩略图/文件名）+ 生成按钮。生成中禁用（需求 4.1/4.3）。
 */
export function ImagePromptBar({
  prompt,
  onPromptChange,
  size,
  quality,
  onSizeChange,
  onQualityChange,
  referenceImage,
  onAttachReference,
  onSubmit,
  loading,
}: ImagePromptBarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const previewUrl = referenceImage ? URL.createObjectURL(referenceImage) : null

  const canSubmit = prompt.trim().length > 0 && !loading

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      if (canSubmit) onSubmit()
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null
    onAttachReference(file)
    // 允许再次选择同名文件
    e.target.value = ''
  }

  return (
    <div className="space-y-3 rounded-2xl border bg-card p-4 shadow-sm">
      <textarea
        value={prompt}
        onChange={(e) => onPromptChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={loading}
        rows={2}
        placeholder="describe the image you want to generate"
        className="flex w-full resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
      />

      {referenceImage && (
        <div className="flex items-center gap-3 rounded-lg border bg-muted/40 p-2">
          {previewUrl && (
            <img
              src={previewUrl}
              alt="参考图缩略图"
              className="h-10 w-10 rounded object-cover"
            />
          )}
          <span className="flex-1 truncate text-xs text-muted-foreground">
            {referenceImage.name}
          </span>
          <button
            type="button"
            onClick={() => onAttachReference(null)}
            disabled={loading}
            aria-label="移除参考图"
            className="rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={size}
          onChange={(e) => onSizeChange(e.target.value)}
          disabled={loading}
          aria-label="图像尺寸"
          className={selectClass}
        >
          {SIZE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        <select
          value={quality}
          onChange={(e) => onQualityChange(e.target.value as ImageParams['quality'])}
          disabled={loading}
          aria-label="图像质量"
          className={selectClass}
        >
          {QUALITY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleFileChange}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={loading}
          onClick={() => fileInputRef.current?.click()}
          className={cn(referenceImage && 'border-amber-500 text-amber-600')}
        >
          <Paperclip className="h-4 w-4" />
          {referenceImage ? '已附参考图' : '附参考图'}
        </Button>

        <div className="ml-auto">
          <Button
            type="button"
            onClick={onSubmit}
            disabled={!canSubmit}
            className="bg-gradient-to-r from-amber-500 to-orange-500 text-white shadow hover:from-amber-500/90 hover:to-orange-500/90"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            {loading ? '生成中…' : '生成'}
          </Button>
        </div>
      </div>
    </div>
  )
}
