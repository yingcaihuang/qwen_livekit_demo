import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { InstanceForm } from '@/components/instances/InstanceForm'
import type { InstanceDetail, InstanceType } from '@/types'

export function InstanceFormPage() {
  const { id } = useParams<{ id: string }>()
  const isEdit = Boolean(id)

  const [initialData, setInitialData] = useState<
    {
      name: string
      endpoint: string
      deployment: string
      description: string
      type: InstanceType
    } | undefined
  >(undefined)
  const [loading, setLoading] = useState(isEdit)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isEdit || !id) return

    async function loadInstance() {
      try {
        const response = await fetch(`/api/instances/${id}`)
        if (!response.ok) {
          throw new Error(`加载实例失败 (${response.status})`)
        }
        const data: InstanceDetail = await response.json()
        setInitialData({
          name: data.name,
          endpoint: data.endpoint,
          deployment: data.deployment,
          description: data.description,
          type: data.type,
        })
      } catch (err) {
        setError(err instanceof Error ? err.message : '加载失败')
      } finally {
        setLoading(false)
      }
    }

    loadInstance()
  }, [isEdit, id])

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-muted-foreground">加载中...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-destructive">{error}</p>
      </div>
    )
  }

  return (
    <div>
      <InstanceForm
        mode={isEdit ? 'edit' : 'create'}
        instanceId={id}
        initialData={initialData}
      />
    </div>
  )
}
