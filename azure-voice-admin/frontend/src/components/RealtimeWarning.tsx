import { AlertTriangle } from 'lucide-react'
import { useSystemStatus } from '@/hooks/useSystemStatus'

export function RealtimeWarning() {
  const status = useSystemStatus()

  if (!status || status.realtime_available) return null

  return (
    <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
      <div className="text-sm">
        <p className="font-medium text-amber-800">⚠️ 实时功能不可用</p>
        <p className="mt-1 text-amber-700">
          当前服务器 CPU 不支持 AVX2 指令集，语音对话、实时翻译和实时转录功能无法使用。
          文本对话和图像生成功能正常工作。
        </p>
        <p className="mt-1 text-amber-600 text-xs">
          解决方案：升级到支持 AVX2 的 CPU 架构（Intel Haswell 2013+ / AMD Excavator 2015+ 及以上）
        </p>
      </div>
    </div>
  )
}
