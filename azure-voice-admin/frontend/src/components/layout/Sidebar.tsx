import { Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Server, History } from 'lucide-react'

const navItems = [
  { label: 'Dashboard', path: '/', icon: LayoutDashboard },
  { label: '实例管理', path: '/instances', icon: Server },
  { label: '会话历史', path: '/history', icon: History },
]

export function Sidebar() {
  const location = useLocation()

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/'
    return location.pathname.startsWith(path)
  }

  return (
    <aside className="flex h-screen w-60 flex-col border-r border-border bg-muted/40">
      <div className="flex h-14 items-center border-b border-border px-6">
        <h1 className="text-lg font-semibold">Voice Admin</h1>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {navItems.map((item) => {
          const Icon = item.icon
          const active = isActive(item.path)
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                active
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              }`}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}
