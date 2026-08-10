import { Navigate } from 'react-router-dom'
import { useAuth } from './AuthProvider'

interface ProtectedRouteProps {
  capability?: string
  children: React.ReactNode
}

export function ProtectedRoute({ capability, children }: ProtectedRouteProps) {
  const { user, capabilities, loading } = useAuth()

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  // Force local users with must_change_password to change their password first
  if (user.must_change_password && user.auth_source === 'local') {
    return <Navigate to="/change-password" replace />
  }

  if (capability && !capabilities.includes(capability)) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
