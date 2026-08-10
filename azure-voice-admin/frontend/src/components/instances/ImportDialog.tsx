import { useState, useRef } from 'react'
import { Upload, X, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface ImportItem {
  name: string
  endpoint: string
  api_key: string
  deployment: string
  type: string
  description: string
  _selected: boolean
}

interface ImportDialogProps {
  open: boolean
  onClose: () => void
  onSuccess: () => void
}

export function ImportDialog({ open, onClose, onSuccess }: ImportDialogProps) {
  const [items, setItems] = useState<ImportItem[]>([])
  const [conflictStrategy, setConflictStrategy] = useState<'skip' | 'update'>('skip')
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<{ created: number; updated: number; skipped: number; errors: string[] } | null>(null)
  const [parseError, setParseError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  if (!open) return null

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setParseError('')
    setResult(null)

    const reader = new FileReader()
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target?.result as string)
        if (!Array.isArray(data)) {
          setParseError('JSON 文件格式无效：应为数组格式')
          return
        }
        const parsed: ImportItem[] = data.map((d: Record<string, string>) => ({
          name: d.name || '',
          endpoint: d.endpoint || '',
          api_key: d.api_key || '',
          deployment: d.deployment || '',
          type: d.type || 'voice',
          description: d.description || '',
          _selected: true,
        }))
        setItems(parsed)
      } catch {
        setParseError('JSON 解析失败，请检查文件格式')
      }
    }
    reader.readAsText(file)
  }

  const toggleItem = (idx: number) => {
    setItems(prev => prev.map((item, i) => i === idx ? { ...item, _selected: !item._selected } : item))
  }

  const updateApiKey = (idx: number, key: string) => {
    setItems(prev => prev.map((item, i) => i === idx ? { ...item, api_key: key } : item))
  }

  const handleImport = async () => {
    const selected = items.filter(i => i._selected)
    if (selected.length === 0) return

    setImporting(true)
    try {
      const payload = {
        instances: selected.map(({ _selected, ...rest }) => rest),
        conflict_strategy: conflictStrategy,
      }
      const res = await fetch('/api/instances/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      if (res.ok) {
        const data = await res.json()
        setResult(data)
        onSuccess()
      } else {
        alert('导入失败')
      }
    } finally {
      setImporting(false)
    }
  }

  const handleClose = () => {
    setItems([])
    setResult(null)
    setParseError('')
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={handleClose}>
      <div className="mx-4 w-full max-w-2xl rounded-xl border bg-background p-6 shadow-xl" onClick={e => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">导入实例配置</h2>
          <button onClick={handleClose} className="rounded p-1 hover:bg-muted"><X className="h-4 w-4" /></button>
        </div>

        {result ? (
          /* Result view */
          <div className="space-y-4">
            <div className="rounded-lg border bg-emerald-50 p-4 text-sm">
              <p className="font-medium text-emerald-800">导入完成</p>
              <ul className="mt-2 space-y-1 text-emerald-700">
                {result.created > 0 && <li>✅ 新建 {result.created} 个实例</li>}
                {result.updated > 0 && <li>🔄 更新 {result.updated} 个实例</li>}
                {result.skipped > 0 && <li>⏭️ 跳过 {result.skipped} 个实例</li>}
              </ul>
              {result.errors.length > 0 && (
                <div className="mt-3 rounded border border-red-200 bg-red-50 p-2">
                  <p className="font-medium text-red-700">错误：</p>
                  <ul className="mt-1 text-xs text-red-600">
                    {result.errors.map((err, i) => <li key={i}>{err}</li>)}
                  </ul>
                </div>
              )}
            </div>
            <div className="flex justify-end">
              <Button onClick={handleClose}>关闭</Button>
            </div>
          </div>
        ) : items.length === 0 ? (
          /* File upload view */
          <div className="space-y-4">
            <div
              className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 hover:border-indigo-400 hover:bg-indigo-50/30 transition"
              onClick={() => fileRef.current?.click()}
            >
              <Upload className="h-8 w-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">点击选择 JSON 文件，或拖入此处</p>
              <p className="text-xs text-muted-foreground">支持从"导出"功能生成的 JSON 配置文件</p>
            </div>
            <input ref={fileRef} type="file" accept=".json" className="hidden" onChange={handleFile} />
            {parseError && (
              <div className="flex items-center gap-2 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                <AlertCircle className="h-4 w-4 shrink-0" />
                {parseError}
              </div>
            )}
            <div className="flex justify-end">
              <Button variant="outline" onClick={handleClose}>取消</Button>
            </div>
          </div>
        ) : (
          /* Preview + import view */
          <div className="space-y-4">
            <div className="max-h-72 overflow-y-auto rounded border">
              <table className="w-full text-sm">
                <thead className="sticky top-0 border-b bg-muted/80">
                  <tr>
                    <th className="px-3 py-2 text-left w-8">
                      <input
                        type="checkbox"
                        checked={items.every(i => i._selected)}
                        onChange={() => {
                          const allSelected = items.every(i => i._selected)
                          setItems(prev => prev.map(i => ({ ...i, _selected: !allSelected })))
                        }}
                        className="h-4 w-4 rounded"
                      />
                    </th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">名称</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">类型</th>
                    <th className="px-3 py-2 text-left font-medium text-muted-foreground">API Key</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, idx) => (
                    <tr key={idx} className="border-b last:border-0 hover:bg-muted/30">
                      <td className="px-3 py-2">
                        <input type="checkbox" checked={item._selected} onChange={() => toggleItem(idx)} className="h-4 w-4 rounded" />
                      </td>
                      <td className="px-3 py-2 font-medium">{item.name}</td>
                      <td className="px-3 py-2 text-xs">{item.type}</td>
                      <td className="px-3 py-2">
                        {item.api_key ? (
                          <span className="text-xs text-emerald-600">✓ 已填</span>
                        ) : (
                          <Input
                            className="h-7 text-xs"
                            placeholder="请填入 API Key"
                            value={item.api_key}
                            onChange={e => updateApiKey(idx, e.target.value)}
                          />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center gap-4">
              <span className="text-sm font-medium">同名实例策略：</span>
              <label className="flex items-center gap-1.5 text-sm cursor-pointer">
                <input type="radio" name="conflict" checked={conflictStrategy === 'skip'} onChange={() => setConflictStrategy('skip')} className="h-4 w-4" />
                跳过
              </label>
              <label className="flex items-center gap-1.5 text-sm cursor-pointer">
                <input type="radio" name="conflict" checked={conflictStrategy === 'update'} onChange={() => setConflictStrategy('update')} className="h-4 w-4" />
                覆盖更新
              </label>
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setItems([])}>重新选择</Button>
              <Button onClick={handleImport} disabled={importing || items.filter(i => i._selected).length === 0}>
                <Upload className="h-4 w-4" />
                {importing ? '导入中...' : `导入 ${items.filter(i => i._selected).length} 个实例`}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
