import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertTriangle, ImageOff, Layers, Loader2 } from 'lucide-react'
import { ImagePromptBar } from '@/components/image/ImagePromptBar'
import { ImageParamsPanel } from '@/components/image/ImageParamsPanel'
import { ImageResultGrid } from '@/components/image/ImageResultGrid'
import { ImageEmptyState } from '@/components/image/ImageEmptyState'
import { ImageMetrics } from '@/components/image/ImageMetrics'
import { ImageQueuePanel } from '@/components/image/ImageQueuePanel'
import { Button } from '@/components/ui/button'
import { toast } from '@/components/ui/toast'
import { cn } from '@/lib/utils'
import type { ImageGeneration, ImageParams, ImageQueue, Instance } from '@/types'

/** 生成任务是否处于进行中（需要继续轮询）。 */
function isPendingStatus(status?: string): boolean {
  return status === 'pending' || status === 'processing'
}

const POLL_INTERVAL_MS = 2000
/** 页面级队列计数轮询间隔（轻量，仅用于按钮徽标）。 */
const QUEUE_COUNT_POLL_MS = 3000

const DEFAULT_PARAMS: ImageParams = {
  size: '1024x1024',
  quality: 'high',
  output_format: 'png',
  compression: 100,
  n: 1,
  input_fidelity: null,
}

export function ImagePlaygroundPage() {
  const [searchParams] = useSearchParams()
  const instanceId = searchParams.get('instance') ?? ''

  const [instanceName, setInstanceName] = useState<string>('')
  const [prompt, setPrompt] = useState('')
  const [params, setParams] = useState<ImageParams>(DEFAULT_PARAMS)
  const [referenceImages, setReferenceImages] = useState<File[]>([])
  const [maskFile, setMaskFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ImageGeneration | null>(null)
  const [queueOpen, setQueueOpen] = useState(false)
  const [queueCount, setQueueCount] = useState(0)

  // 轻量拉取队列总数，用于「队列」按钮上的实时徽标。
  const refreshQueueCount = useCallback(async () => {
    try {
      const res = await fetch('/api/images/queue')
      if (!res.ok) return
      const data = (await res.json()) as ImageQueue
      setQueueCount(data.total)
    } catch {
      // 静默失败，下个周期继续尝试
    }
  }, [])

  // 页面级队列计数轮询（每 ~3s），提供实时徽标。
  useEffect(() => {
    void refreshQueueCount()
    const timer = setInterval(refreshQueueCount, QUEUE_COUNT_POLL_MS)
    return () => clearInterval(timer)
  }, [refreshQueueCount])

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

  // 轮询：任务处于 pending/processing 时每 2s 拉取一次详情，直至终态或卸载。
  // 依赖 result?.id + result?.status，避免终态后继续轮询。
  const resultId = result?.id
  const resultStatus = result?.status
  useEffect(() => {
    if (!resultId || !isPendingStatus(resultStatus)) return

    let cancelled = false
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`/api/images/${resultId}`)
        if (!res.ok) return
        const data = (await res.json()) as ImageGeneration
        if (!cancelled) setResult(data)
      } catch {
        // 轮询失败保持静默，下个周期继续尝试
      }
    }, POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [resultId, resultStatus])

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
      if (params.input_fidelity) {
        formData.append('input_fidelity', params.input_fidelity)
      }
      referenceImages.forEach((f) => formData.append('files', f))
      if (maskFile) {
        formData.append('mask', maskFile)
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

      // 异步入队成功（202 pending）：提示用户任务已进入后台队列。
      if (isPendingStatus(data.status)) {
        toast({
          title: '已加入生成队列',
          description: '任务在后台生成，可离开页面，稍后在会话历史查看',
          action: { label: '查看队列', onClick: () => setQueueOpen(true) },
        })
        void refreshQueueCount()
      }
    } catch (err) {
      // 生成失败展示错误横幅，并保留参数便于重试（需求 9.2）
      setError(err instanceof Error ? err.message : '生成失败，请重试')
    } finally {
      setLoading(false)
    }
  }, [instanceId, prompt, params, referenceImages, maskFile, refreshQueueCount])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="bg-gradient-to-r from-amber-500 to-orange-500 bg-clip-text text-3xl font-bold tracking-tight text-transparent">
            图像生成 / Image Playground
          </h1>
          <p className="text-sm text-muted-foreground">
            {instanceName ? `实例：${instanceName}` : '通过 Azure OpenAI 生成或编辑图像'}
          </p>
        </div>

        <Button
          variant="outline"
          onClick={() => setQueueOpen(true)}
          className="relative shrink-0 border-amber-200 bg-gradient-to-br from-amber-50 to-orange-50 text-amber-700 hover:from-amber-100 hover:to-orange-100 hover:text-amber-800"
        >
          <Layers className="h-4 w-4" aria-hidden="true" />
          队列
          {queueCount > 0 && (
            <span
              className={cn(
                'absolute -right-2 -top-2 flex h-5 min-w-5 items-center justify-center rounded-full',
                'bg-gradient-to-br from-orange-500 to-rose-500 px-1 text-[11px] font-bold text-white shadow-md',
              )}
            >
              {queueCount}
            </span>
          )}
        </Button>
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
              referenceImages={referenceImages}
              onAddReferences={(files) => setReferenceImages((prev) => [...prev, ...files])}
              onRemoveReference={(idx) => setReferenceImages((prev) => prev.filter((_, i) => i !== idx))}
              maskFile={maskFile}
              onSetMask={setMaskFile}
              onSubmit={handleSubmit}
              loading={loading}
            />

            {error && (
              <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {!result ? (
              <ImageEmptyState />
            ) : isPendingStatus(result.status) ? (
              <div className="flex min-h-[320px] flex-col items-center justify-center gap-4 rounded-2xl border border-amber-200/60 bg-gradient-to-br from-amber-50/70 to-orange-50/50 p-10 text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-500 to-orange-500 text-white shadow-lg">
                  <Loader2 className="h-8 w-8 animate-spin" aria-hidden="true" />
                </div>
                <div className="space-y-1">
                  <p className="text-lg font-semibold text-foreground">正在生成图像…</p>
                  <p className="text-sm text-muted-foreground">
                    可以离开页面，稍后在会话历史查看结果
                  </p>
                </div>
                {result.prompt && (
                  <p className="max-w-md whitespace-pre-wrap rounded-lg bg-background/70 px-4 py-2 text-sm text-muted-foreground shadow-sm">
                    {result.prompt}
                  </p>
                )}
              </div>
            ) : result.status === 'failed' ? (
              <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="space-y-1">
                  <p className="font-semibold">{result.error_message || '生成失败'}</p>
                  <p className="text-destructive/80">请调整提示词或参数后重新生成。</p>
                </div>
              </div>
            ) : (
              <>
                <ImageResultGrid result={result} />
                <ImageMetrics
                  startedAt={result.started_at}
                  endedAt={result.ended_at}
                  durationMs={result.duration_ms}
                  ttfbMs={result.ttfb_ms}
                />
              </>
            )}
          </div>

          {/* 侧栏：参数面板 */}
          <div className="lg:col-span-1">
            <ImageParamsPanel
              params={params}
              onChange={updateParams}
              disabled={loading}
              hasReferenceImages={referenceImages.length > 0}
            />
          </div>
        </div>
      )}

      <ImageQueuePanel open={queueOpen} onOpenChange={setQueueOpen} />
    </div>
  )
}
