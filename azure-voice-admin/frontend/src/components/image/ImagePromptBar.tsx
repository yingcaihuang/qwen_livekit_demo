import { useRef } from 'react'
import { Paperclip, Sparkles, X, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { toast } from '@/components/ui/toast'
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

/** 参考图最大数量 */
const MAX_REFERENCE_COUNT = 10
/** 单文件最大体积 (50MB) */
const MAX_FILE_SIZE = 50 * 1024 * 1024

interface ImagePromptBarProps {
  prompt: string
  onPromptChange: (value: string) => void
  size: string
  quality: ImageParams['quality']
  onSizeChange: (value: string) => void
  onQualityChange: (value: ImageParams['quality']) => void
  referenceImages: File[]
  onAddReferences: (files: File[]) => void
  onRemoveReference: (index: number) => void
  maskFile: File | null
  onSetMask: (file: File | null) => void
  onSubmit: () => void
  loading: boolean
}

const selectClass =
  'h-9 rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50'

/**
 * 图像提示词输入栏：prompt 文本框 + 内联 size/quality 选择 +
 * 多参考图按钮（附件后展示缩略图网格）+ 遮罩图 + 生成按钮。
 * 支持多文件选择和客户端校验（需求 4.1–4.7, 5.1–5.5）。
 */
export function ImagePromptBar({
  prompt,
  onPromptChange,
  size,
  quality,
  onSizeChange,
  onQualityChange,
  referenceImages,
  onAddReferences,
  onRemoveReference,
  maskFile,
  onSetMask,
  onSubmit,
  loading,
}: ImagePromptBarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const maskInputRef = useRef<HTMLInputElement>(null)

  const canSubmit = prompt.trim().length > 0 && !loading

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      if (canSubmit) onSubmit()
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(e.target.files || [])
    e.target.value = ''
    processReferenceFiles(selectedFiles)
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    e.stopPropagation()
    const droppedFiles = Array.from(e.dataTransfer.files)
    processReferenceFiles(droppedFiles)
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault()
    e.stopPropagation()
  }

  /** 校验并添加参考图文件 */
  function processReferenceFiles(selectedFiles: File[]) {
    const validFiles: File[] = []
    for (const file of selectedFiles) {
      // Format check
      if (!file.type.match(/^image\/(png|jpeg|jpg)$/)) {
        toast({ title: '格式不支持', description: `仅支持 PNG 和 JPG 格式（${file.name}）` })
        continue
      }
      // Size check (50MB)
      if (file.size > MAX_FILE_SIZE) {
        toast({ title: '文件过大', description: `图片大小不能超过 50MB（${file.name}）` })
        continue
      }
      validFiles.push(file)
    }

    // Count check
    const totalCount = referenceImages.length + validFiles.length
    if (totalCount > MAX_REFERENCE_COUNT) {
      toast({ title: '数量超限', description: '参考图最多 10 张' })
      const allowed = MAX_REFERENCE_COUNT - referenceImages.length
      if (allowed > 0) {
        onAddReferences(validFiles.slice(0, allowed))
      }
    } else if (validFiles.length > 0) {
      onAddReferences(validFiles)
    }
  }

  function handleMaskChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null
    e.target.value = ''
    if (file && !file.type.match(/^image\/png$/)) {
      toast({ title: '格式不支持', description: '遮罩图必须是 PNG 格式' })
      return
    }
    if (file && file.size > MAX_FILE_SIZE) {
      toast({ title: '文件过大', description: '遮罩图大小不能超过 50MB' })
      return
    }
    onSetMask(file)
  }

  return (
    <div
      className="space-y-3 rounded-2xl border bg-card p-4 shadow-sm"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
    >
      <textarea
        value={prompt}
        onChange={(e) => onPromptChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={loading}
        rows={2}
        placeholder="describe the image you want to generate"
        className="flex w-full resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
      />

      {/* 参考图缩略图网格 */}
      {referenceImages.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 p-2">
          {referenceImages.map((file, idx) => (
            <div key={idx} className="relative group">
              <img
                src={URL.createObjectURL(file)}
                alt={`参考图 ${idx + 1}`}
                className="h-12 w-12 rounded object-cover border"
              />
              <button
                type="button"
                onClick={() => onRemoveReference(idx)}
                disabled={loading}
                className="absolute -right-1 -top-1 hidden group-hover:flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-white text-[10px]"
              >
                &times;
              </button>
            </div>
          ))}
          <span className="text-xs text-muted-foreground">
            {referenceImages.length}/{MAX_REFERENCE_COUNT}
          </span>
        </div>
      )}

      {/* 遮罩图上传区域（仅在有参考图时显示） */}
      {referenceImages.length > 0 && (
        <div className="flex items-center gap-2">
          <input
            ref={maskInputRef}
            type="file"
            accept="image/png"
            className="hidden"
            onChange={handleMaskChange}
          />
          {maskFile ? (
            <div className="flex items-center gap-2 rounded-lg border bg-muted/40 px-2 py-1">
              <img
                src={URL.createObjectURL(maskFile)}
                alt="遮罩图"
                className="h-8 w-8 rounded object-cover border"
              />
              <span className="text-xs text-muted-foreground">{maskFile.name}</span>
              <button
                type="button"
                onClick={() => onSetMask(null)}
                disabled={loading}
                className="rounded-full p-0.5 text-muted-foreground hover:text-foreground"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ) : (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={loading}
              onClick={() => maskInputRef.current?.click()}
              className="text-xs text-muted-foreground"
            >
              + 遮罩图（可选，PNG）
            </Button>
          )}
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
          multiple
          accept="image/png,image/jpeg"
          className="hidden"
          onChange={handleFileChange}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={loading}
          onClick={() => fileInputRef.current?.click()}
          className={cn(referenceImages.length > 0 && 'border-amber-500 text-amber-600')}
        >
          <Paperclip className="h-4 w-4" />
          {referenceImages.length > 0 ? `参考图 (${referenceImages.length})` : '附参考图'}
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
