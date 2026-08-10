import { Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Server, History, Users, Shield, Settings, LogOut, KeyRound } from 'lucide-react'
import { useAuth } from '@/components/auth/AuthProvider'

interface NavItem {
  label: string
  path: string
  icon: React.ComponentType<{ className?: string }>
  capability?: string
}

const navItems: NavItem[] = [
  { label: 'Dashboard', path: '/', icon: LayoutDashboard, capability: 'dashboard:read' },
  { label: '实例管理', path: '/instances', icon: Server, capability: 'instance:read' },
  { label: '会话历史', path: '/history', icon: History },
]

const adminItems: NavItem[] = [
  { label: '用户管理', path: '/admin/users', icon: Users, capability: 'user:manage' },
  { label: '组映射', path: '/admin/group-mappings', icon: Shield, capability: 'role:manage' },
  { label: 'SSO 配置', path: '/admin/sso', icon: Settings, capability: 'sso:manage' },
]

export function Sidebar() {
  const location = useLocation()
  const { capabilities, user, logout } = useAuth()

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/'
    return location.pathname.startsWith(path)
  }

  const visibleNav = navItems.filter(item => !item.capability || capabilities.includes(item.capability))
  const visibleAdmin = adminItems.filter(item => !item.capability || capabilities.includes(item.capability))

  return (
    <aside className="flex h-screen w-60 flex-col border-r border-border bg-muted/40">
      <div className="flex h-14 items-center border-b border-border px-6">
        <h1 className="text-lg font-semibold">AI 测试平台</h1>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {visibleNav.map((item) => {
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

        {visibleAdmin.length > 0 && (
          <>
            <div className="my-3 border-t border-border" />
            <p className="px-3 text-xs font-medium uppercase text-muted-foreground">管理后台</p>
            {visibleAdmin.map((item) => {
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
          </>
        )}
      </nav>

      {/* User info + logout at bottom */}
      {user && (
        <div className="border-t border-border p-3 space-y-1">
          <div className="flex items-center justify-between px-3 py-2">
            <span className="text-xs text-muted-foreground truncate">{user.username}</span>
            <div className="flex items-center gap-1">
              {user.auth_source === 'local' && (
                <Link to="/change-password" className="text-muted-foreground hover:text-foreground" title="修改密码">
                  <KeyRound className="h-4 w-4" />
                </Link>
              )}
              <button onClick={logout} className="text-muted-foreground hover:text-foreground" title="退出登录">
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}
