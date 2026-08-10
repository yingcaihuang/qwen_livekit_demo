import { SlidersHorizontal } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import type { ImageParams } from '@/types'

/** 图像格式选项（至少含 png，需求 4.1） */
const FORMAT_OPTIONS = [
  { value: 'png', label: 'PNG' },
  { value: 'jpeg', label: 'JPEG' },
  { value: 'webp', label: 'WebP' },
] as const

const MAX_VARIATIONS = 10

interface ImageParamsPanelProps {
  params: ImageParams
  onChange: (patch: Partial<ImageParams>) => void
  disabled?: boolean
  hasReferenceImages?: boolean
}

const selectClass =
  'h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50'

/** 约束到闭区间 [min, max] */
function clamp(value: number, min: number, max: number): number {
  if (Number.isNaN(value)) return min
  return Math.max(min, Math.min(max, value))
}

/**
 * 参数面板：压缩等级滑块（0-100，默认 100，约束区间 — 需求 4.7）、
 * 图像格式下拉、变体数量滑块（默认 1，>= 1 — 需求 4.6）。
 * 参数状态由页面提升管理，此处仅受控展示与回调。
 */
export function ImageParamsPanel({ params, onChange, disabled, hasReferenceImages }: ImageParamsPanelProps) {
  return (
    <Card className="shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-orange-500 text-white">
            <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
          </span>
          Parameters
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Compression Level */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="compression">Compression Level</Label>
            <span className="text-sm font-semibold text-amber-600">
              {params.compression}
            </span>
          </div>
          <input
            id="compression"
            type="range"
            min={0}
            max={100}
            step={1}
            value={params.compression}
            disabled={disabled}
            onChange={(e) =>
              onChange({ compression: clamp(Number(e.target.value), 0, 100) })
            }
            className="w-full accent-amber-500 disabled:opacity-50"
          />
          <p className="text-xs text-muted-foreground">
            仅在 JPEG / WebP 格式下生效
          </p>
        </div>

        {/* Image Format */}
        <div className="space-y-2">
          <Label htmlFor="output_format">Image Format</Label>
          <select
            id="output_format"
            value={params.output_format}
            disabled={disabled}
            onChange={(e) => onChange({ output_format: e.target.value })}
            className={selectClass}
          >
            {FORMAT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Number of variations */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="variations">Number of variations</Label>
            <span className="text-sm font-semibold text-amber-600">{params.n}</span>
          </div>
          <input
            id="variations"
            type="range"
            min={1}
            max={MAX_VARIATIONS}
            step={1}
            value={params.n}
            disabled={disabled}
            onChange={(e) =>
              onChange({ n: clamp(Number(e.target.value), 1, MAX_VARIATIONS) })
            }
            className="w-full accent-amber-500 disabled:opacity-50"
          />
        </div>

        {/* Input Fidelity (editing mode only) */}
        {hasReferenceImages && (
          <div className="space-y-2">
            <Label htmlFor="input_fidelity">Input Fidelity</Label>
            <select
              id="input_fidelity"
              value={params.input_fidelity ?? ''}
              disabled={disabled}
              onChange={(e) =>
                onChange({
                  input_fidelity: (e.target.value || null) as ImageParams['input_fidelity'],
                })
              }
              className={selectClass}
            >
              <option value="">Default</option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
            <p className="text-xs text-muted-foreground">
              控制输出与参考图的匹配程度
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
