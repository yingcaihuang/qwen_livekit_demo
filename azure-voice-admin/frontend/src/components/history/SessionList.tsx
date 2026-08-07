import { SessionRow } from './SessionRow'
import type { Session } from '@/types'

interface SessionListProps {
  sessions: Session[]
  onDelete: (id: string) => void
}

export function SessionList({ sessions, onDelete }: SessionListProps) {
  if (sessions.length === 0) {
    return (
      <div className="flex items-center justify-center p-12 border rounded-lg">
        <p className="text-muted-foreground">暂无会话记录</p>
      </div>
    )
  }

  return (
    <div className="border rounded-lg overflow-hidden">
      <table className="w-full">
        <thead className="bg-muted/50">
          <tr>
            <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
              实例名称
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
              开始时间
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
              时长
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
              Token 数量
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
              状态
            </th>
            <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">
              操作
            </th>
          </tr>
        </thead>
        <tbody>
          {sessions.map((session) => (
            <SessionRow key={session.id} session={session} onDelete={onDelete} />
          ))}
        </tbody>
      </table>
    </div>
  )
}
