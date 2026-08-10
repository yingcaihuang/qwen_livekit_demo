import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

interface AuthUser {
  id: string
  username: string
  must_change_password?: boolean
  auth_source?: string
}

interface AuthState {
  user: AuthUser | null
  roles: string[]
  capabilities: string[]
  loading: boolean
  csrfToken: string | null
  logout: () => Promise<void>
  refreshAuth: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [roles, setRoles] = useState<string[]>([])
  const [capabilities, setCapabilities] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [csrfToken, setCsrfToken] = useState<string | null>(null)

  const fetchMe = async () => {
    try {
      const res = await fetch('/api/auth/me', { credentials: 'include' })
      if (res.ok) {
        const data = await res.json()
        setUser({ id: data.id, username: data.username, must_change_password: data.must_change_password, auth_source: data.auth_source })
        setRoles(data.roles)
        setCapabilities(data.capabilities)
        if (data.csrf_token) {
          setCsrfToken(data.csrf_token)
        }
      } else {
        setUser(null)
        setRoles([])
        setCapabilities([])
      }
    } catch {
      setUser(null)
      setRoles([])
      setCapabilities([])
    } finally {
      setLoading(false)
    }
  }

  const logout = async () => {
    const res = await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
    const data = await res.json().catch(() => ({}))
    setUser(null)
    setRoles([])
    setCapabilities([])
    setCsrfToken(null)
    // If SSO user, redirect to IdP end_session endpoint
    if (data.end_session_url) {
      window.location.href = data.end_session_url
    } else {
      window.location.href = '/login'
    }
  }

  useEffect(() => { fetchMe() }, [])

  return (
    <AuthContext.Provider value={{ user, roles, capabilities, loading, csrfToken, logout, refreshAuth: fetchMe }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
