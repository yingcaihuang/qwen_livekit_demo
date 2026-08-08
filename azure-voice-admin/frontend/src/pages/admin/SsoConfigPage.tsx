import { useEffect, useState } from 'react'
import { Globe, Copy, Check } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import { toast } from '@/components/ui/toast'
import { SamlConfigPanel } from '@/components/admin/SamlConfigPanel'

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
    groups_source: 'userinfo' as string,
    login_button_enabled: false,
    cookie_secure: false,
  })
  const [discovering, setDiscovering] = useState(false)
  const [secretSet, setSecretSet] = useState(false)
  const [copiedField, setCopiedField] = useState<string | null>(null)
  const [scimTokenSet, setScimTokenSet] = useState(false)
  const [scimToken, setScimToken] = useState('')

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
          groups_source: d.groups_source || 'userinfo',
          login_button_enabled: d.login_button_enabled,
          cookie_secure: d.cookie_secure,
        }))
        setSecretSet(d.client_secret_set)
        setScimTokenSet(d.scim_token_set)
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
    toast({ title: '✅ 已复制到剪贴板', duration: 2000 })
    setCopiedField(field)
    setTimeout(() => setCopiedField(null), 2000)
  }

  const handleGenerateScimToken = async () => {
    if (scimTokenSet && !confirm('重新生成将使旧 Token 立即失效，Authentik 需要更新。确定继续？')) return
    const res = await fetch('/api/admin/sso-config/scim-token', { method: 'POST', credentials: 'include' })
    if (res.ok) {
      const d = await res.json()
      setScimToken(d.scim_token)
      setScimTokenSet(true)
    }
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
          配置单点登录，支持 OIDC（Authentik / Keycloak）和 SAML 2.0 协议
        </p>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="oidc">
        <TabsList>
          <TabsTrigger value="oidc">OIDC</TabsTrigger>
          <TabsTrigger value="saml">SAML</TabsTrigger>
        </TabsList>

        {/* OIDC Tab */}
        <TabsContent value="oidc">
          <div className="space-y-6">
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
                    <Label>End Session Endpoint <span className="text-xs font-normal text-muted-foreground">(自动发现可回填)</span></Label>
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
                  <div className="space-y-2">
                    <Label>Groups 来源</Label>
                    <select
                      value={form.groups_source}
                      onChange={(e) => setForm((f) => ({ ...f, groups_source: e.target.value }))}
                      className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    >
                      <option value="userinfo">Userinfo 端点</option>
                      <option value="id_token">ID Token</option>
                    </select>
                    <p className="text-xs text-muted-foreground">
                      选择从哪里读取用户的 groups claim。ID Token 受 Scope Mapping 表达式控制；Userinfo 可能返回完整组列表。
                    </p>
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

            {/* Section 4: SCIM Provisioning */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">SCIM 用户同步</CardTitle>
                <CardDescription>通过 SCIM v2 协议从 Authentik 自动同步用户和组变更</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center gap-4">
                  <div className="flex-1">
                    <p className="text-sm">SCIM Token: {scimTokenSet ? <span className="text-emerald-600 font-medium">已生成</span> : <span className="text-muted-foreground">未生成</span>}</p>
                    {scimToken && (
                      <div className="mt-2 flex items-center gap-2">
                        <code className="flex-1 rounded-md border bg-muted px-3 py-1.5 text-xs font-mono break-all">{scimToken}</code>
                        <Button variant="ghost" size="sm" onClick={() => copyToClipboard(scimToken, 'scim')}>
                          {copiedField === 'scim' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                        </Button>
                      </div>
                    )}
                    <p className="mt-1 text-xs text-muted-foreground">⚠️ Token 仅在生成时显示一次，请立即复制</p>
                  </div>
                  <Button variant="outline" onClick={handleGenerateScimToken}>
                    {scimTokenSet ? '重新生成' : '生成 Token'}
                  </Button>
                </div>
                <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-3 space-y-1.5">
                  <p className="text-xs font-medium text-amber-800">在 Authentik 中配置 SCIM Provider：</p>
                  <ol className="list-decimal pl-5 space-y-1 text-xs text-amber-700">
                    <li>进入 Applications → Providers → Create → <strong>SCIM Provider</strong></li>
                    <li>URL 填入: <code className="rounded bg-white px-1.5 py-0.5 border text-xs">{`${window.location.origin}/scim/v2`}</code></li>
                    <li>Token 填入上方生成的 SCIM Token</li>
                    <li>点 Finish 保存后，进入 Applications → 你的应用 → 关联此 SCIM Provider</li>
                    <li>Authentik 会自动同步用户/组变更到本平台</li>
                  </ol>
                </div>
              </CardContent>
            </Card>

            {/* Authentik URI Reference */}
            <Card className="border-blue-200 bg-blue-50/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold text-blue-800">
                  📋 以下 URI 需要在 Authentik Provider 配置中填写
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center gap-3">
                  <span className="w-52 shrink-0 text-xs font-medium text-blue-700">Redirect URI:</span>
                  <code className="flex-1 rounded-md border bg-white px-3 py-1.5 text-xs text-foreground">
                    {`${window.location.origin}/api/auth/sso/callback`}
                  </code>
                  <Button variant="ghost" size="sm" className="shrink-0 text-blue-600"
                    onClick={() => copyToClipboard(`${window.location.origin}/api/auth/sso/callback`, 'redirect')}>
                    {copiedField === 'redirect' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
                <div className="flex items-center gap-3">
                  <span className="w-52 shrink-0 text-xs font-medium text-blue-700">Post Logout Redirect URI:</span>
                  <code className="flex-1 rounded-md border bg-white px-3 py-1.5 text-xs text-foreground">
                    {`${window.location.origin}/login`}
                  </code>
                  <Button variant="ghost" size="sm" className="shrink-0 text-blue-600"
                    onClick={() => copyToClipboard(`${window.location.origin}/login`, 'logout')}>
                    {copiedField === 'logout' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
                <div className="flex items-center gap-3">
                  <span className="w-52 shrink-0 text-xs font-medium text-blue-700">Front-Channel Logout URI:</span>
                  <code className="flex-1 rounded-md border bg-white px-3 py-1.5 text-xs text-foreground">
                    {`${window.location.origin}/api/auth/sso/frontchannel-logout`}
                  </code>
                  <Button variant="ghost" size="sm" className="shrink-0 text-blue-600"
                    onClick={() => copyToClipboard(`${window.location.origin}/api/auth/sso/frontchannel-logout`, 'frontchannel')}>
                    {copiedField === 'frontchannel' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
                <div className="flex items-center gap-3">
                  <span className="w-52 shrink-0 text-xs font-medium text-blue-700">Back-Channel Logout URI:</span>
                  <code className="flex-1 rounded-md border bg-white px-3 py-1.5 text-xs text-foreground">
                    {`${window.location.origin}/api/auth/sso/backchannel-logout`}
                  </code>
                  <Button variant="ghost" size="sm" className="shrink-0 text-blue-600"
                    onClick={() => copyToClipboard(`${window.location.origin}/api/auth/sso/backchannel-logout`, 'backchannel')}>
                    {copiedField === 'backchannel' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Authentik Logout Configuration Guide */}
            <Card className="border-amber-200 bg-amber-50/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold text-amber-800">
                  🔐 Authentik 注销配置指南（Single Logout）
                </CardTitle>
                <CardDescription className="text-xs text-amber-700">
                  配置后，当用户从 Authentik 或其他关联应用退出时，本平台的会话也会自动失效
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                {/* Method 1: Front-Channel */}
                <div className="rounded-lg border border-amber-200 bg-white p-4 space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs font-bold text-emerald-700">推荐 · 内网可用</span>
                    <h4 className="font-semibold text-foreground">方式一：正向通道（Front-Channel）</h4>
                  </div>
                  <p className="text-xs text-muted-foreground">通过浏览器 iframe 注销，无需公网可达。适用于内网/本地开发环境。</p>
                  <ol className="list-decimal pl-5 space-y-1 text-xs text-foreground">
                    <li>进入 Authentik → <strong>Applications → Providers</strong>，编辑你的 OAuth2 Provider</li>
                    <li>在 <strong>注销 URI (Logout URI)</strong> 字段填入：<code className="rounded bg-muted px-1.5 py-0.5">{`${window.location.origin}/api/auth/sso/frontchannel-logout`}</code></li>
                    <li><strong>注销方法</strong> 选择：<strong>正向通道（Front-channel）</strong></li>
                    <li>点击 <strong>保存 / Update</strong></li>
                  </ol>
                  <p className="text-xs text-amber-700 italic">原理：用户在 Authentik 注销时，浏览器会加载一个隐藏 iframe 访问此 URL，自动携带 Cookie 使会话失效。</p>
                </div>

                {/* Method 2: Back-Channel */}
                <div className="rounded-lg border border-amber-200 bg-white p-4 space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-blue-100 px-2 py-0.5 text-xs font-bold text-blue-700">需公网可达</span>
                    <h4 className="font-semibold text-foreground">方式二：反向通道（Back-Channel）</h4>
                  </div>
                  <p className="text-xs text-muted-foreground">Authentik 服务器直接 POST 签名 Token 到本应用。即使用户浏览器已关闭也能注销。需要 Authentik 能访问本应用地址。</p>
                  <ol className="list-decimal pl-5 space-y-1 text-xs text-foreground">
                    <li>进入 Authentik → <strong>Applications → Providers</strong>，编辑你的 OAuth2 Provider</li>
                    <li>在 <strong>注销 URI (Logout URI)</strong> 字段填入：<code className="rounded bg-muted px-1.5 py-0.5">{`${window.location.origin}/api/auth/sso/backchannel-logout`}</code></li>
                    <li><strong>注销方法</strong> 选择：<strong>反向通道（Back-channel）</strong></li>
                    <li>点击 <strong>保存 / Update</strong></li>
                  </ol>
                  <p className="text-xs text-amber-700 italic">⚠️ 要求：Authentik 服务器必须能通过网络访问到上述 URI。内网/localhost 环境下 Authentik 在公网时此方式不可用，请改用正向通道。</p>
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
        </TabsContent>

        {/* SAML Tab */}
        <TabsContent value="saml">
          <SamlConfigPanel />
        </TabsContent>
      </Tabs>
    </div>
  )
}
