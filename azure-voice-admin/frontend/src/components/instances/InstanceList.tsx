import { InstanceCard } from './InstanceCard'
import type { Instance } from '@/types'

interface InstanceListProps {
  instances: Instance[]
  onDelete: (id: string) => void
}

export function InstanceList({ instances, onDelete }: InstanceListProps) {
  if (instances.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <p className="text-muted-foreground">
          还没有配置实例，点击上方按钮创建第一个实例
        </p>
      </div>
    )
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {instances.map((instance) => (
        <InstanceCard key={instance.id} instance={instance} onDelete={onDelete} />
      ))}
    </div>
  )
}
