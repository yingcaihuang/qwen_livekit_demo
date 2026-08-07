import { Boxes } from 'lucide-react'
import { InstanceCard } from './InstanceCard'
import type { Instance } from '@/types'

interface InstanceListProps {
  instances: Instance[]
  onDelete: (id: string) => void
}

export function InstanceList({ instances, onDelete }: InstanceListProps) {
  if (instances.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed bg-gradient-to-br from-muted/40 to-transparent p-14 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-500/10 text-indigo-500">
          <Boxes className="h-8 w-8" aria-hidden="true" />
        </div>
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
