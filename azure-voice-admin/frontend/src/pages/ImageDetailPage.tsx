import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useApi } from '@/hooks/useApi'
import { ImageDetail, type ImageDetailData } from '@/components/history/ImageDetail'

/**
 * 图像生成详情页（路由 `/history/image/:id`）。
 * 拉取 `GET /api/images/{id}` 并渲染图片网格 / prompt / 参数 / 用量（需求 5.3）。
 */
export function ImageDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data, loading, error } = useApi<ImageDetailData>(`/api/images/${id}`)

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-muted-foreground">加载中...</p>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-destructive">
          {error ? `加载失败: ${error.message}` : '图像记录不存在'}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate('/history')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="bg-gradient-to-r from-amber-500 to-orange-500 bg-clip-text text-2xl font-bold tracking-tight text-transparent">
          图像生成详情
        </h1>
      </div>

      <ImageDetail data={data} />
    </div>
  )
}
