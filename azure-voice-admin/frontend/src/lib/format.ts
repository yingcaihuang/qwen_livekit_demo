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

/**
 * 将完整的 Azure 端点 URL 压缩为简短标签。
 * - 空值 => ''
 * - 取 URL 的 pathname（去掉查询串）
 * - 若路径包含 `/openai/`，返回其后的部分
 *   （如 `https://.../openai/v1/responses?x=1` -> `v1/responses`；
 *    `.../openai/v1/chat/completions` -> `v1/chat/completions`）
 * 解析失败时回退到字符串操作，保持健壮。
 */
export function formatEndpoint(url?: string | null): string {
  if (!url) return ''

  const fromPath = (path: string): string => {
    // 去掉查询串与哈希
    let p = path.split('?')[0]?.split('#')[0] ?? ''
    const marker = '/openai/'
    const idx = p.indexOf(marker)
    if (idx !== -1) {
      p = p.slice(idx + marker.length)
    }
    // 去掉首尾多余的斜杠
    return p.replace(/^\/+/, '').replace(/\/+$/, '')
  }

  try {
    const parsed = new URL(url)
    return fromPath(parsed.pathname)
  } catch {
    // 非法/相对 URL：尽力从字符串中提取路径部分
    const withoutScheme = url.replace(/^[a-z]+:\/\//i, '')
    const slashIdx = withoutScheme.indexOf('/')
    const path = slashIdx === -1 ? '' : withoutScheme.slice(slashIdx)
    return fromPath(path || url)
  }
}
