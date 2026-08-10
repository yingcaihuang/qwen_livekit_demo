import { useState } from 'react'
import { Download, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface ExportInstance {
  id: string
  name: string
  type: string
}

interface ExportDialogProps {
  open: boolean
  onClose: () => void
  instances: ExportInstance[]
}

export function ExportDialog({ open, onClose, instances }: ExportDialogProps) {
  const [includeApiKey, setIncludeApiKey] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set(instances.map(i => i.id)))
  const [exporting, setExporting] = useState(false)

  if (!open) return null

  const toggleId = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selectedIds.size === instances.length) setSelectedIds(new Set())
    else setSelectedIds(new Set(instances.map(i => i.id)))
  }

  const handleExport = async () => {
    const ids = Array.from(selectedIds)
    if (ids.length === 0) return

    setExporting(true)
    try {
      const res = await fetch('/api/instances/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ instance_ids: ids, include_api_key: includeApiKey }),
      })
      if (!res.ok) {
        alert('导出失败')
        return
      }
      const data = await res.json()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `instances-export-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      onClose()
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="mx-4 w-full max-w-lg rounded-xl border bg-background p-6 shadow-xl" onClick={e => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">导出实例配置</h2>
          <button onClick={onClose} className="rounded p-1 hover:bg-muted"><X className="h-4 w-4" /></button>
        </div>

        <div className="mb-4 max-h-60 overflow-y-auto rounded border">
          <div className="border-b px-3 py-2">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input type="checkbox" checked={selectedIds.size === instances.length} onChange={toggleAll} className="h-4 w-4 rounded" />
              全选 ({selectedIds.size}/{instances.length})
            </label>
          </div>
          {instances.map(inst => (
            <label key={inst.id} className="flex items-center gap-2 px-3 py-2 hover:bg-muted/30 text-sm cursor-pointer">
              <input type="checkbox" checked={selectedIds.has(inst.id)} onChange={() => toggleId(inst.id)} className="h-4 w-4 rounded" />
              <span className="font-medium">{inst.name}</span>
              <span className="text-xs text-muted-foreground">({inst.type})</span>
            </label>
          ))}
        </div>

        <label className="mb-4 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={includeApiKey} onChange={e => setIncludeApiKey(e.target.checked)} className="h-4 w-4 rounded" />
          包含 API Key（明文，注意安全）
        </label>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button onClick={handleExport} disabled={exporting || selectedIds.size === 0}>
            <Download className="h-4 w-4" />
            {exporting ? '导出中...' : `导出 ${selectedIds.size} 个实例`}
          </Button>
        </div>
      </div>
    </div>
  )
}
