import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertTriangle, ImageOff } from 'lucide-react'
import { ImagePromptBar } from '@/components/image/ImagePromptBar'
import { ImageParamsPanel } from '@/components/image/ImageParamsPanel'
import { ImageResultGrid } from '@/components/image/ImageResultGrid'
import { ImageEmptyState } from '@/components/image/ImageEmptyState'
import type { ImageGeneration, ImageParams, Instance } from '@/types'

const DEFAULT_PARAMS: ImageParams = {
  size: '1024x1024',
  quality: 'high',
  output_format: 'png',
  compression: 100,
  n: 1,
}

export function ImagePlaygroundPage() {
  const [searchParams] = useSearchParams()
  const instanceId = searchParams.get('instance') ?? ''

  const [instanceName, setInstanceName] = useState<string>('')
  const [prompt, setPrompt] = useState('')
  const [params, setParams] = useState<ImageParams>(DEFAULT_PARAMS)
  const [referenceImage, setReferenceImage] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ImageGeneration | null>(null)

  // 拉取实例信息用于标题展示（失败不阻塞页面）
  useEffect(() => {
    if (!instanceId) return
    let cancelled = false
    fetch(`/api/instances/${instanceId}`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch instance')
        return res.json()
      })
      .then((data: Instance) => {
        if (!cancelled) setInstanceName(data.name)
      })
      .catch(() => {
        if (!cancelled) setInstanceName('')
      })
    return () => {
      cancelled = true
    }
  }, [instanceId])

  const updateParams = useCallback((patch: Partial<ImageParams>) => {
    setParams((prev) => ({ ...prev, ...patch }))
  }, [])

  const handleSubmit = useCallback(async () => {
    if (!instanceId) {
      setError('未选择实例，请从实例列表进入图像生成。')
      return
    }
    if (!prompt.trim()) return

    setLoading(true)
    setError(null)

    try {
      const formData = new FormData()
      formData.append('instance_id', instanceId)
      formData.append('prompt', prompt.trim())
      formData.append('size', params.size)
      formData.append('quality', params.quality)
      formData.append('output_format', params.output_format)
      formData.append('compression', String(params.compression))
      formData.append('n', String(params.n))
      if (referenceImage) {
        formData.append('file', referenceImage)
      }

      const response = await fetch('/api/images/generations', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const errData = await response.json().catch(() => null)
        const detail = errData?.detail
        throw new Error(
          typeof detail === 'string'
            ? detail
            : `生成失败 (HTTP ${response.status})`,
        )
      }

      const data = (await response.json()) as ImageGeneration
      setResult(data)
    } catch (err) {
      // 生成失败展示错误横幅，并保留参数便于重试（需求 9.2）
      setError(err instanceof Error ? err.message : '生成失败，请重试')
    } finally {
      setLoading(false)
    }
  }, [instanceId, prompt, params, referenceImage])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-1">
        <h1 className="bg-gradient-to-r from-amber-500 to-orange-500 bg-clip-text text-3xl font-bold tracking-tight text-transparent">
          图像生成 / Image Playground
        </h1>
        <p className="text-sm text-muted-foreground">
          {instanceName ? `实例：${instanceName}` : '通过 Azure OpenAI 生成或编辑图像'}
        </p>
      </div>

      {!instanceId ? (
        <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 rounded-2xl border border-dashed p-10 text-center text-muted-foreground">
          <ImageOff className="h-10 w-10" aria-hidden="true" />
          <p>未选择实例，请从实例列表选择一个图像实例后再进入。</p>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          {/* 主区：输入栏 + 结果 */}
          <div className="space-y-6 lg:col-span-2">
            <ImagePromptBar
              prompt={prompt}
              onPromptChange={setPrompt}
              size={params.size}
              quality={params.quality}
              onSizeChange={(size) => updateParams({ size })}
              onQualityChange={(quality) => updateParams({ quality })}
              referenceImage={referenceImage}
              onAttachReference={setReferenceImage}
              onSubmit={handleSubmit}
              loading={loading}
            />

            {error && (
              <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {result ? (
              <ImageResultGrid result={result} />
            ) : (
              <ImageEmptyState />
            )}
          </div>

          {/* 侧栏：参数面板 */}
          <div className="lg:col-span-1">
            <ImageParamsPanel
              params={params}
              onChange={updateParams}
              disabled={loading}
            />
          </div>
        </div>
      )}
    </div>
  )
}
