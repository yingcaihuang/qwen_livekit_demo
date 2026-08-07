import { ArrowDown, ArrowUp, Calendar, ImageIcon, Layers } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { TypeBadge } from '@/components/instances/TypeBadge'
import { ImageMetrics } from '@/components/image/ImageMetrics'

/**
 * 图像生成详情数据形态，对应后端 `GET /api/images/{generation_id}` 的行字典：
 * 顶层含 size/quality/output_format/compression/n，同时在 `params` 中冗余一份。
 * 这里以顶层字段为主、`params` 兜底，兼容两种响应形态。
 */
export interface ImageDetailData {
  id: string
  instance_id: string
  prompt: string
  images: string[]
  input_tokens: number
  output_tokens: number
  has_reference: boolean
  created_at: string
  started_at?: string | null
  ended_at?: string | null
  duration_ms?: number | null
  ttfb_ms?: number | null
  status?: string
  error_message?: string | null
  size?: string
  quality?: string
  output_format?: string
  compression?: number
  n?: number
  params?: {
    size?: string
    quality?: string
    output_format?: string
    compression?: number
    n?: number
  }
}

interface ImageDetailProps {
  data: ImageDetailData
}

function formatDateTime(isoString: string): string {
  const date = new Date(isoString)
  if (Number.isNaN(date.getTime())) return isoString
  return date.toLocaleString('zh-CN')
}

interface ParamPillProps {
  label: string
  value: string | number
}

function ParamPill({ label, value }: ParamPillProps) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border bg-background px-3 py-1 text-xs shadow-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-semibold text-foreground">{value}</span>
    </span>
  )
}

/**
 * 图像生成详情视图：图片网格 + prompt + 参数 + 用量 + 元数据。
 * 沿用彩色渐变视觉风格（需求 5.3）。
 */
export function ImageDetail({ data }: ImageDetailProps) {
  const size = data.size ?? data.params?.size ?? '—'
  const quality = data.quality ?? data.params?.quality ?? '—'
  const outputFormat = data.output_format ?? data.params?.output_format ?? '—'
  const compression = data.compression ?? data.params?.compression
  const variations = data.n ?? data.params?.n ?? data.images.length
  const images = data.images ?? []

  return (
    <div className="space-y-6">
      {/* Prompt */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
            <TypeBadge type="image" />
            提示词
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="whitespace-pre-wrap text-sm text-foreground">{data.prompt || '—'}</p>
        </CardContent>
      </Card>

      {/* Params + usage */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
            <Layers className="h-4 w-4 text-amber-500" />
            生成参数
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <ParamPill label="尺寸" value={size} />
            <ParamPill label="质量" value={quality} />
            <ParamPill label="格式" value={outputFormat} />
            {compression !== undefined && <ParamPill label="压缩" value={compression} />}
            <ParamPill label="变体数" value={variations} />
            <ParamPill label="参考图" value={data.has_reference ? '是' : '否'} />
          </div>
          <div className="flex flex-wrap items-center gap-4 border-t pt-3 text-sm">
            <span className="inline-flex items-center gap-1.5">
              <ArrowUp className="h-4 w-4 text-violet-500" />
              <span className="text-muted-foreground">输入 Tokens</span>
              <span className="font-semibold">{(data.input_tokens ?? 0).toLocaleString()}</span>
            </span>
            <span className="inline-flex items-center gap-1.5">
              <ArrowDown className="h-4 w-4 text-amber-500" />
              <span className="text-muted-foreground">输出 Tokens</span>
              <span className="font-semibold">{(data.output_tokens ?? 0).toLocaleString()}</span>
            </span>
            <span className="inline-flex items-center gap-1.5 text-muted-foreground">
              <Calendar className="h-4 w-4 text-indigo-500" />
              {formatDateTime(data.created_at)}
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Performance metrics（旧记录无计时字段时自动隐藏） */}
      <ImageMetrics
        startedAt={data.started_at}
        endedAt={data.ended_at}
        durationMs={data.duration_ms}
        ttfbMs={data.ttfb_ms}
      />

      {/* Error (if any) */}
      {data.error_message && (
        <Card className="border-destructive">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-destructive">错误信息</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-destructive">{data.error_message}</p>
          </CardContent>
        </Card>
      )}

      {/* Image grid */}
      <div>
        <h2 className="mb-3 flex items-center gap-1.5 text-lg font-semibold">
          <ImageIcon className="h-5 w-5 text-amber-500" />
          生成结果
          <span className="text-sm font-normal text-muted-foreground">（{images.length} 张）</span>
        </h2>
        {images.length > 0 ? (
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
        ) : (
          <div className="flex items-center justify-center rounded-lg border p-8">
            <p className="text-muted-foreground">暂无图片</p>
          </div>
        )}
      </div>
    </div>
  )
}
