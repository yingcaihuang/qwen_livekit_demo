import { Inbox } from 'lucide-react'
import { SessionRow } from './SessionRow'
import type { Session } from '@/types'

interface SessionListProps {
  sessions: Session[]
  onDelete: (id: string) => void
}

const HEADERS = ['实例名称', '开始时间', '时长', 'Token 数量', '状态', '操作'] as const

export function SessionList({ sessions, onDelete }: SessionListProps) {
  if (sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed bg-gradient-to-br from-muted/40 to-transparent p-14 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-sky-500/10 text-sky-500">
          <Inbox className="h-8 w-8" aria-hidden="true" />
        </div>
        <p className="text-muted-foreground">暂无会话记录</p>
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-xl border shadow-sm">
      <table className="w-full">
        <thead className="bg-gradient-to-r from-muted/60 to-muted/30">
          <tr>
            {HEADERS.map((header) => (
              <th
                key={header}
                className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y">
          {sessions.map((session) => (
            <SessionRow key={session.id} session={session} onDelete={onDelete} />
          ))}
        </tbody>
      </table>
    </div>
  )
}
