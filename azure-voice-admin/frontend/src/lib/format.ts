/**
 * 通用格式化工具：耗时与时间展示。
 */

/**
 * 将毫秒格式化为可读耗时字符串。
 * - null / undefined => "—"
 * - < 1000ms => 整数毫秒，如 "850 ms"
 * - >= 1000ms => 秒（2 位小数，去除多余的尾随零），如 "3.24 s" / "2 s"
 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return '—'
  if (ms < 1000) {
    return `${Math.round(ms)} ms`
  }
  const seconds = ms / 1000
  // 保留 2 位小数后去除尾随的 0（如 "3.20" -> "3.2"，"2.00" -> "2"）
  const trimmed = seconds.toFixed(2).replace(/\.?0+$/, '')
  return `${trimmed} s`
}

/**
 * 将 ISO 时间字符串格式化为本地化（zh-CN）日期时间。
 * 空值或无法解析时返回 "—"。
 */
export function formatDateTime(s?: string | null): string {
  if (!s) return '—'
  const date = new Date(s)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN')
}
