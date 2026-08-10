import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/components/auth/AuthProvider'
import { Shield } from 'lucide-react'

export function LoginPage() {
  const navigate = useNavigate()
  const { user, refreshAuth } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [ssoEnabled, setSsoEnabled] = useState(false)
  const [samlEnabled, setSamlEnabled] = useState(false)

  // Redirect if already logged in
  useEffect(() => {
    if (user) {
      if (user.must_change_password && user.auth_source === 'local') {
        navigate('/change-password', { replace: true })
      } else {
        navigate('/', { replace: true })
      }
    }
  }, [user, navigate])

  // Check SSO config
  useEffect(() => {
    fetch('/api/auth/sso/public-config')
      .then(r => r.json())
      .then(d => {
        setSsoEnabled(d.login_button_enabled)
        setSamlEnabled(d.saml_login_enabled)
      })
      .catch(() => {})
  }, [])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username, password }),
      })
      if (res.ok) {
        const data = await res.json()
        await refreshAuth()
        if (data.must_change_password) {
          navigate('/change-password', { replace: true })
        } else {
          navigate('/', { replace: true })
        }
      } else {
        const data = await res.json().catch(() => ({}))
        setError(data.detail || '登录失败')
      }
    } catch {
      setError('网络错误，请检查连接')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-100">
      <div className="w-full max-w-md space-y-6 rounded-2xl bg-white p-8 shadow-xl">
        {/* Logo / Title */}
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900">Azure OpenAI 测试平台</h1>
          <p className="mt-2 text-sm text-gray-500">请登录以继续</p>
        </div>

        {/* Login Form */}
        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label htmlFor="username" className="block text-sm font-medium text-gray-700">
              用户名
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              required
              autoComplete="username"
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700">
              密码
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              required
              autoComplete="current-password"
            />
          </div>

          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground shadow-sm hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? '登录中...' : '登录'}
          </button>
        </form>

        {/* SSO Divider + Buttons */}
        {(ssoEnabled || samlEnabled) && (
          <>
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="bg-white px-2 text-gray-400">或</span>
              </div>
            </div>

            <div className="space-y-3">
              {ssoEnabled && (
                <a
                  href="/api/auth/sso/login"
                  className="flex w-full items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
                >
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 10.5V6.75a4.5 4.5 0 1 1 9 0v3.75M3.75 21.75h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H3.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
                  </svg>
                  统一认证入口
                </a>
              )}

              {samlEnabled && (
                <a
                  href="/api/saml/login"
                  className="flex w-full items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
                >
                  <Shield className="h-4 w-4" />
                  SAML 企业登录
                </a>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
