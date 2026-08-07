import { ImagePlus } from 'lucide-react'

/**
 * 图像 Playground 空态。
 * 在当前视图尚未产出任何 Image_Generation 时展示（需求 4.4）。
 */
export function ImageEmptyState() {
  return (
    <div className="flex min-h-[320px] flex-col items-center justify-center gap-4 rounded-2xl border border-dashed border-muted-foreground/30 bg-gradient-to-br from-amber-50/60 to-orange-50/40 p-10 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-500 to-orange-500 text-white shadow-lg">
        <ImagePlus className="h-8 w-8" aria-hidden="true" />
      </div>
      <div className="space-y-1">
        <p className="text-lg font-semibold text-foreground">
          Generate an image to get started
        </p>
        <p className="text-sm text-muted-foreground">
          输入提示词并点击生成，结果将在此处展示
        </p>
      </div>
    </div>
  )
}
