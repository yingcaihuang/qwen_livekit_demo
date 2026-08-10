import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Mic, MessageSquare, Image, Languages, FileText } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { InstanceType } from '@/types'

interface InstanceFormData {
  name: string
  endpoint: string
  api_key: string
  deployment: string
  description: string
  type: InstanceType | ''
}

interface InstanceFormProps {
  mode: 'create' | 'edit'
  instanceId?: string
  initialData?: Partial<InstanceFormData>
}

interface FieldErrors {
  name?: string
  endpoint?: string
  api_key?: string
  deployment?: string
  type?: string
}

const TYPE_OPTIONS: ReadonlyArray<{
  value: InstanceType
  label: string
  icon: LucideIcon
  gradient: string
}> = [
  { value: 'voice', label: '语音', icon: Mic, gradient: 'from-indigo-500 to-violet-500' },
  { value: 'chat', label: '对话', icon: MessageSquare, gradient: 'from-emerald-500 to-teal-500' },
  { value: 'image', label: '图像', icon: Image, gradient: 'from-amber-500 to-orange-500' },
  { value: 'translate', label: '翻译', icon: Languages, gradient: 'from-cyan-500 to-blue-500' },
  { value: 'transcribe', label: '转录', icon: FileText, gradient: 'from-rose-500 to-pink-500' },
]

export function InstanceForm({ mode, instanceId, initialData }: InstanceFormProps) {
  const navigate = useNavigate()
  const [form, setForm] = useState<InstanceFormData>({
    name: '',
    endpoint: '',
    api_key: '',
    deployment: '',
    description: '',
    type: '',
  })
  const [errors, setErrors] = useState<FieldErrors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (initialData) {
      setForm((prev) => ({
        ...prev,
        name: initialData.name ?? '',
        endpoint: initialData.endpoint ?? '',
        api_key: initialData.api_key ?? '',
        deployment: initialData.deployment ?? '',
        description: initialData.description ?? '',
        type: initialData.type ?? '',
      }))
    }
  }, [initialData])

  function validate(): boolean {
    const newErrors: FieldErrors = {}

    if (!form.name.trim()) {
      newErrors.name = '名称不能为空'
    }
    if (!form.endpoint.trim()) {
      newErrors.endpoint = 'Endpoint 不能为空'
    }
    if (mode === 'create' && !form.api_key.trim()) {
      newErrors.api_key = 'API Key 不能为空'
    }
    if (!form.deployment.trim()) {
      newErrors.deployment = 'Deployment 不能为空'
    }
    if (mode === 'create' && !form.type) {
      newErrors.type = '请选择实例类型'
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitError(null)

    if (!validate()) return

    setSubmitting(true)
    try {
      const url =
        mode === 'create' ? '/api/instances' : `/api/instances/${instanceId}`
      const method = mode === 'create' ? 'POST' : 'PUT'

      const body: Record<string, string> = {
        name: form.name.trim(),
        endpoint: form.endpoint.trim(),
        deployment: form.deployment.trim(),
        description: form.description.trim(),
      }

      // For create, always include api_key and type; for edit, only include
      // api_key if non-empty and omit type entirely (type is immutable).
      if (mode === 'create') {
        body.api_key = form.api_key.trim()
        if (form.type) {
          body.type = form.type
        }
      } else if (form.api_key.trim()) {
        body.api_key = form.api_key.trim()
      }

      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!response.ok) {
        const data = await response.json().catch(() => null)
        const detail = data?.detail || `请求失败 (${response.status})`
        setSubmitError(typeof detail === 'string' ? detail : JSON.stringify(detail))
        return
      }

      navigate('/instances')
    } catch {
      setSubmitError('网络请求失败，请检查连接')
    } finally {
      setSubmitting(false)
    }
  }

  function handleChange(field: keyof InstanceFormData, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }))
    // Clear field error on input change
    if (errors[field as keyof FieldErrors]) {
      setErrors((prev) => ({ ...prev, [field]: undefined }))
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>{mode === 'create' ? '创建实例' : '编辑实例'}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {submitError && (
            <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
              {submitError}
            </div>
          )}

          <div className="space-y-2">
            <Label>类型 *</Label>
            <div className="grid grid-cols-5 gap-3">
              {TYPE_OPTIONS.map((option) => {
                const Icon = option.icon
                const selected = form.type === option.value
                return (
                  <button
                    key={option.value}
                    type="button"
                    disabled={mode === 'edit'}
                    aria-pressed={selected}
                    onClick={() => {
                      setForm((prev) => ({ ...prev, type: option.value }))
                      if (errors.type) {
                        setErrors((prev) => ({ ...prev, type: undefined }))
                      }
                    }}
                    className={cn(
                      'flex flex-col items-center gap-2 rounded-xl border-2 p-3 transition',
                      selected
                        ? 'border-transparent bg-gradient-to-br text-white shadow-sm ' + option.gradient
                        : 'border-input bg-transparent text-muted-foreground hover:border-muted-foreground/40',
                      mode === 'edit' && 'cursor-not-allowed opacity-60'
                    )}
                  >
                    <Icon className="h-5 w-5" aria-hidden="true" />
                    <span className="text-sm font-medium">{option.label}</span>
                  </button>
                )
              })}
            </div>
            {mode === 'edit' && (
              <p className="text-xs text-muted-foreground">类型创建后不可修改</p>
            )}
            {errors.type && (
              <p className="text-sm text-destructive">{errors.type}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="name">名称 *</Label>
            <Input
              id="name"
              value={form.name}
              onChange={(e) => handleChange('name', e.target.value)}
              placeholder="例如：GPT-4o Realtime 生产环境"
            />
            {errors.name && (
              <p className="text-sm text-destructive">{errors.name}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="endpoint">Endpoint *</Label>
            <Input
              id="endpoint"
              value={form.endpoint}
              onChange={(e) => handleChange('endpoint', e.target.value)}
              placeholder="例如：https://xxx.openai.azure.com"
            />
            {errors.endpoint && (
              <p className="text-sm text-destructive">{errors.endpoint}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="api_key">
              API Key {mode === 'create' ? '*' : ''}
            </Label>
            <Input
              id="api_key"
              type="password"
              value={form.api_key}
              onChange={(e) => handleChange('api_key', e.target.value)}
              placeholder={
                mode === 'edit' ? '留空则不修改' : '输入 Azure API Key'
              }
            />
            {errors.api_key && (
              <p className="text-sm text-destructive">{errors.api_key}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="deployment">Deployment *</Label>
            <Input
              id="deployment"
              value={form.deployment}
              onChange={(e) => handleChange('deployment', e.target.value)}
              placeholder="例如：gpt-4o-realtime-preview"
            />
            <p className="text-xs text-muted-foreground">
              对话类型可用英文逗号分隔填写多个模型，例如：gpt-5.5, gpt-4o；测试时可在对话页选择
            </p>
            {errors.deployment && (
              <p className="text-sm text-destructive">{errors.deployment}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">描述</Label>
            <textarea
              id="description"
              value={form.description}
              onChange={(e) => handleChange('description', e.target.value)}
              placeholder="可选的描述信息"
              rows={3}
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>
        </CardContent>
        <CardFooter className="gap-2">
          <Button type="submit" disabled={submitting}>
            {submitting ? '提交中...' : mode === 'create' ? '创建' : '保存'}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate('/instances')}
          >
            取消
          </Button>
        </CardFooter>
      </Card>
    </form>
  )
}
