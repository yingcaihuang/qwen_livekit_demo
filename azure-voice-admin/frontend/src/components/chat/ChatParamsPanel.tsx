import { Settings2, Thermometer, Hash, Gauge, Timer, Zap } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { formatDuration } from '@/lib/format'
import type { ChatParams, ChatTiming, TokenUsage } from '@/types'

interface ChatParamsPanelProps {
  params: ChatParams
  onChange: (params: ChatParams) => void
  /** 最近一次响应的用量（可用时展示） */
  usage?: TokenUsage | null
  /** 最近一次响应的性能计时（可用时展示） */
  timing?: ChatTiming | null
}

/** 将 temperature 约束到 [0, 2]（需求 2.5）。 */
function clampTemperature(value: number): number {
  if (Number.isNaN(value)) return 0
  return Math.min(2, Math.max(0, value))
}

/**
 * 参数面板：system prompt / temperature(0-2) / max_tokens(正整数或留空)。
 * 状态由上层页面持有并通过 onChange 回传（需求 2.4/2.5/2.6）。
 */
export function ChatParamsPanel({ params, onChange, usage, timing }: ChatParamsPanelProps) {
  const handleSystemPrompt = (system_prompt: string) => {
    onChange({ ...params, system_prompt })
  }

  const handleTemperature = (raw: number) => {
    onChange({ ...params, temperature: clampTemperature(raw) })
  }

  const handleMaxTokens = (raw: string) => {
    if (raw.trim() === '') {
      onChange({ ...params, max_tokens: null })
      return
    }
    const parsed = Math.floor(Number(raw))
    if (Number.isNaN(parsed) || parsed < 1) {
      // 非正整数则视为未设置（null 透传）
      onChange({ ...params, max_tokens: null })
      return
    }
    onChange({ ...params, max_tokens: parsed })
  }

  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto p-4">
      <div className="flex items-center gap-2">
        <div
          className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-sm"
          aria-hidden="true"
        >
          <Settings2 className="h-4 w-4" />
        </div>
        <h2 className="text-sm font-semibold">对话参数</h2>
      </div>

      {/* System prompt */}
      <div className="space-y-1.5">
        <Label htmlFor="system-prompt">System Prompt</Label>
        <textarea
          id="system-prompt"
          value={params.system_prompt}
          onChange={(e) => handleSystemPrompt(e.target.value)}
          rows={4}
          placeholder="设置系统提示词，为对话设定角色或规则…"
          className="min-h-[88px] w-full resize-y rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
      </div>

      {/* Temperature */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <Label htmlFor="temperature" className="flex items-center gap-1.5">
            <Thermometer className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
            Temperature
          </Label>
          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
            {params.temperature.toFixed(1)}
          </span>
        </div>
        <input
          id="temperature"
          type="range"
          min={0}
          max={2}
          step={0.1}
          value={params.temperature}
          onChange={(e) => handleTemperature(Number(e.target.value))}
          className="w-full accent-indigo-600"
        />
        <div className="flex justify-between text-[10px] text-muted-foreground">
          <span>0（确定）</span>
          <span>2（发散）</span>
        </div>
      </div>

      {/* Max tokens */}
      <div className="space-y-1.5">
        <Label htmlFor="max-tokens" className="flex items-center gap-1.5">
          <Hash className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          Max Tokens
        </Label>
        <Input
          id="max-tokens"
          type="number"
          min={1}
          step={1}
          value={params.max_tokens ?? ''}
          onChange={(e) => handleMaxTokens(e.target.value)}
          placeholder="留空表示不限制"
        />
        <p className="text-[10px] text-muted-foreground">正整数；留空则由模型默认决定。</p>
      </div>

      {/* Token usage & timing */}
      {(usage || timing) && (
        <div className="mt-auto space-y-3">
          {usage && (
            <div className="rounded-lg border bg-muted/40 p-3">
              <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Gauge className="h-3.5 w-3.5" aria-hidden="true" />
                Token 用量
              </div>
              <div className="grid grid-cols-2 gap-2 text-center">
                <div className="rounded-md bg-background px-2 py-1.5 shadow-sm">
                  <div className="font-mono text-sm font-semibold text-indigo-600">
                    {usage.input_tokens}
                  </div>
                  <div className="text-[10px] text-muted-foreground">输入</div>
                </div>
                <div className="rounded-md bg-background px-2 py-1.5 shadow-sm">
                  <div className="font-mono text-sm font-semibold text-violet-600">
                    {usage.output_tokens}
                  </div>
                  <div className="text-[10px] text-muted-foreground">输出</div>
                </div>
              </div>
            </div>
          )}

          {timing && (
            <div className="rounded-lg border bg-muted/40 p-3">
              <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Timer className="h-3.5 w-3.5" aria-hidden="true" />
                性能指标
              </div>
              <div className="grid grid-cols-2 gap-2 text-center">
                <div className="rounded-md bg-background px-2 py-1.5 shadow-sm">
                  <div className="flex items-center justify-center gap-1 font-mono text-sm font-semibold text-sky-600">
                    <Zap className="h-3 w-3" aria-hidden="true" />
                    {formatDuration(timing.ttfb_ms)}
                  </div>
                  <div className="text-[10px] text-muted-foreground">首字响应</div>
                </div>
                <div className="rounded-md bg-background px-2 py-1.5 shadow-sm">
                  <div className="flex items-center justify-center gap-1 font-mono text-sm font-semibold text-amber-600">
                    <Timer className="h-3 w-3" aria-hidden="true" />
                    {formatDuration(timing.total_ms)}
                  </div>
                  <div className="text-[10px] text-muted-foreground">总耗时</div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
