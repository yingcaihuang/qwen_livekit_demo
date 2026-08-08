import { useEffect, useState } from 'react'
import { Globe, Copy, Check } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

export function SsoConfigPage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [form, setForm] = useState({
    issuer: '',
    discovery_url: '',
    client_id: '',
    client_secret: '',
    authorization_endpoint: '',
    token_endpoint: '',
    userinfo_endpoint: '',
    jwks_uri: '',
    end_session_endpoint: '',
    redirect_uri: '',
    scopes: 'openid profile email groups',
    groups_claim: 'groups',
    login_button_enabled: false,
    cookie_secure: false,
  })
  const [discovering, setDiscovering] = useState(false)
  const [secretSet, setSecretSet] = useState(false)
  const [copiedField, setCopiedField] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/admin/sso-config', { credentials: 'include' })
      .then((r) => r.json())
      .then((d) => {
        setForm((f) => ({
          ...f,
          issuer: d.issuer || '',
          discovery_url: d.discovery_url || '',
          client_id: d.client_id || '',
          authorization_endpoint: d.authorization_endpoint || '',
          token_endpoint: d.token_endpoint || '',
          userinfo_endpoint: d.userinfo_endpoint || '',
          jwks_uri: d.jwks_uri || '',
          end_session_endpoint: d.end_session_endpoint || '',
          redirect_uri: d.redirect_uri || '',
          scopes: d.scopes || 'openid profile email groups',
          groups_claim: d.groups_claim || 'groups',
          login_button_enabled: d.login_button_enabled,
          cookie_secure: d.cookie_secure,
        }))
        setSecretSet(d.client_secret_set)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleDiscover = async () => {
    if (!form.discovery_url.trim()) return
    setDiscovering(true)
    setMessage('')
    try {
      const res = await fetch('/api/admin/sso-config/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ discovery_url: form.discovery_url.trim() }),
      })
      if (res.ok) {
        const d = await res.json()
        setForm((f) => ({
          ...f,
          issuer: d.issuer || f.issuer,
          authorization_endpoint: d.authorization_endpoint || f.authorization_endpoint,
          token_endpoint: d.token_endpoint || f.token_endpoint,
          userinfo_endpoint: d.userinfo_endpoint || f.userinfo_endpoint,
          jwks_uri: d.jwks_uri || f.jwks_uri,
          end_session_endpoint: d.end_session_endpoint || f.end_session_endpoint,
        }))
        setMessage('✅ 端点已自动填充，请检查后保存')
      } else {
        const d = await res.json().catch(() => ({}))
        setMessage(`❌ ${d.detail || '自动发现失败'}`)
      }
    } catch {
      setMessage('❌ 网络错误')
    } finally {
      setDiscovering(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setMessage('')
    const body: Record<string, unknown> = { ...form }
    if (!body.client_secret) delete body.client_secret
    try {
      const res = await fetch('/api/admin/sso-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(body),
      })
      if (res.ok) {
        const d = await res.json()
        setSecretSet(d.client_secret_set)
        setForm((f) => ({ ...f, client_secret: '' }))
        setMessage('✅ 配置已保存')
      } else {
        const d = await res.json().catch(() => ({}))
        setMessage(`❌ ${d.detail || '保存失败'}`)
      }
    } catch {
      setMessage('❌ 网络错误')
    } finally {
      setSaving(false)
    }
  }

  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard.writeText(text)
    setCopiedField(field)
    setTimeout(() => setCopiedField(null), 2000)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-muted-foreground">加载中...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-1">
        <h1 className="bg-gradient-to-r from-indigo-600 to-violet-500 bg-clip-text text-3xl font-bold tracking-tight text-transparent">
          SSO 配置
        </h1>
        <p className="text-sm text-muted-foreground">
          配置 OpenID Connect 单点登录，支持 Authentik / Keycloak 等 IdP
        </p>
      </div>

      {/* Section 1: Basic Info */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Globe className="h-5 w-5 text-indigo-500" />
            基础信息
          </CardTitle>
          <CardDescription>配置 IdP 的基本连接信息和客户端凭证</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Issuer</Label>
              <Input
                value={form.issuer}
                onChange={(e) => setForm((f) => ({ ...f, issuer: e.target.value }))}
                placeholder="https://authentik.example.com/application/o/app/"
              />
            </div>
            <div className="space-y-2">
              <Label>Discovery URL</Label>
              <div className="flex gap-2">
                <Input
                  className="flex-1"
                  value={form.discovery_url}
                  onChange={(e) => setForm((f) => ({ ...f, discovery_url: e.target.value }))}
                  placeholder="https://.../.well-known/openid-configuration"
                />
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleDiscover}
                  disabled={discovering || !form.discovery_url.trim()}
                  className="shrink-0"
                >
                  {discovering ? '发现中...' : '自动发现'}
                </Button>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Client ID</Label>
              <Input
                value={form.client_id}
                onChange={(e) => setForm((f) => ({ ...f, client_id: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>
                Client Secret{' '}
                {secretSet && (
                  <span className="text-xs font-normal text-emerald-600">(已设置)</span>
                )}
              </Label>
              <Input
                type="password"
                value={form.client_secret}
                onChange={(e) => setForm((f) => ({ ...f, client_secret: e.target.value }))}
                placeholder={secretSet ? '留空不修改' : '输入密钥'}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Section 2: Endpoints */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">端点配置</CardTitle>
          <CardDescription>
            OAuth2 / OIDC 各端点地址，可通过 Discovery URL 自动填充
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Authorization Endpoint</Label>
              <Input
                value={form.authorization_endpoint}
                onChange={(e) =>
                  setForm((f) => ({ ...f, authorization_endpoint: e.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Token Endpoint</Label>
              <Input
                value={form.token_endpoint}
                onChange={(e) => setForm((f) => ({ ...f, token_endpoint: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>Userinfo Endpoint</Label>
              <Input
                value={form.userinfo_endpoint}
                onChange={(e) => setForm((f) => ({ ...f, userinfo_endpoint: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>JWKS URI</Label>
              <Input
                value={form.jwks_uri}
                onChange={(e) => setForm((f) => ({ ...f, jwks_uri: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>End Session Endpoint</Label>
              <Input
                value={form.end_session_endpoint}
                onChange={(e) => setForm((f) => ({ ...f, end_session_endpoint: e.target.value }))}
                placeholder="https://authentik.example.com/application/o/app/end-session/"
              />
            </div>
            <div className="space-y-2">
              <Label>Redirect URI</Label>
              <div className="flex gap-2">
                <Input
                  className="flex-1"
                  value={form.redirect_uri}
                  onChange={(e) => setForm((f) => ({ ...f, redirect_uri: e.target.value }))}
                  placeholder="例如: https://your-domain/api/auth/sso/callback"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setForm((f) => ({
                      ...f,
                      redirect_uri: `${window.location.origin}/api/auth/sso/callback`,
                    }))
                  }
                  className="shrink-0"
                >
                  自动填写
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Section 3: Security & Options */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">安全与选项</CardTitle>
          <CardDescription>Scope、Claim 字段配置与安全选项</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Scopes</Label>
              <Input
                value={form.scopes}
                onChange={(e) => setForm((f) => ({ ...f, scopes: e.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label>Groups Claim 字段名</Label>
              <Input
                value={form.groups_claim}
                onChange={(e) => setForm((f) => ({ ...f, groups_claim: e.target.value }))}
              />
            </div>
          </div>

          <div className="space-y-3 pt-2">
            <div className="flex items-center gap-3">
              <label className="relative inline-flex cursor-pointer items-center">
                <input
                  type="checkbox"
                  checked={form.login_button_enabled}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, login_button_enabled: e.target.checked }))
                  }
                  className="peer sr-only"
                />
                <div className="h-5 w-9 rounded-full bg-gray-300 after:absolute after:left-[2px] after:top-[2px] after:h-4 after:w-4 after:rounded-full after:bg-white after:transition-all peer-checked:bg-primary peer-checked:after:translate-x-full" />
              </label>
              <span className="text-sm text-foreground">在登录页显示"统一认证入口"按钮</span>
            </div>
            <div className="flex items-center gap-3">
              <label className="relative inline-flex cursor-pointer items-center">
                <input
                  type="checkbox"
                  checked={form.cookie_secure}
                  onChange={(e) => setForm((f) => ({ ...f, cookie_secure: e.target.checked }))}
                  className="peer sr-only"
                />
                <div className="h-5 w-9 rounded-full bg-gray-300 after:absolute after:left-[2px] after:top-[2px] after:h-4 after:w-4 after:rounded-full after:bg-white after:transition-all peer-checked:bg-primary peer-checked:after:translate-x-full" />
              </label>
              <span className="text-sm text-foreground">
                Cookie Secure 模式（仅 HTTPS 环境启用）
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Authentik URI Reference */}
      <Card className="border-blue-200 bg-blue-50/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold text-blue-800">
            📋 以下 URI 需要在 Authentik 应用配置中填写
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-center gap-3">
            <span className="w-52 shrink-0 text-xs font-medium text-blue-700">Redirect URI:</span>
            <code className="flex-1 rounded-md border bg-white px-3 py-1.5 text-xs text-foreground">
              {`${window.location.origin}/api/auth/sso/callback`}
            </code>
            <Button
              variant="ghost"
              size="sm"
              className="shrink-0 text-blue-600"
              onClick={() =>
                copyToClipboard(
                  `${window.location.origin}/api/auth/sso/callback`,
                  'redirect'
                )
              }
            >
              {copiedField === 'redirect' ? (
                <Check className="h-4 w-4" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </Button>
          </div>
          <div className="flex items-center gap-3">
            <span className="w-52 shrink-0 text-xs font-medium text-blue-700">
              Post Logout Redirect URI:
            </span>
            <code className="flex-1 rounded-md border bg-white px-3 py-1.5 text-xs text-foreground">
              {`${window.location.origin}/login`}
            </code>
            <Button
              variant="ghost"
              size="sm"
              className="shrink-0 text-blue-600"
              onClick={() =>
                copyToClipboard(`${window.location.origin}/login`, 'logout')
              }
            >
              {copiedField === 'logout' ? (
                <Check className="h-4 w-4" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Save */}
      <div className="flex items-center gap-4">
        <Button onClick={handleSave} disabled={saving} size="lg">
          {saving ? '保存中...' : '保存配置'}
        </Button>
        {message && (
          <span
            className={cn(
              'text-sm',
              message.startsWith('✅') ? 'text-emerald-600' : 'text-destructive'
            )}
          >
            {message}
          </span>
        )}
      </div>
    </div>
  )
}
