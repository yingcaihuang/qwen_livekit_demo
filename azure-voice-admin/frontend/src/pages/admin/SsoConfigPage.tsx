import { useEffect, useState } from 'react'

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
  })
  const [discovering, setDiscovering] = useState(false)
  const [secretSet, setSecretSet] = useState(false)

  useEffect(() => {
    fetch('/api/admin/sso-config', { credentials: 'include' })
      .then(r => r.json())
      .then(d => {
        setForm(f => ({
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
        setForm(f => ({
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
    if (!body.client_secret) delete body.client_secret // don't send empty string
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
        setForm(f => ({ ...f, client_secret: '' }))
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

  if (loading) return <div className="p-6">加载中...</div>

  const inputCls = "mt-1 block w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
  const labelCls = "block text-sm font-medium text-gray-700"

  return (
    <div className="space-y-6 p-6">
      <h2 className="text-xl font-bold">SSO 配置</h2>
      <div className="max-w-3xl space-y-4 rounded-lg border p-6">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div><label className={labelCls}>Issuer</label><input className={inputCls} value={form.issuer} onChange={e => setForm(f => ({...f, issuer: e.target.value}))} placeholder="https://authentik.example.com/application/o/app/" /></div>
          <div><label className={labelCls}>Discovery URL</label>
            <div className="mt-1 flex gap-2">
              <input className="block flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary" value={form.discovery_url} onChange={e => setForm(f => ({...f, discovery_url: e.target.value}))} placeholder="https://.../.well-known/openid-configuration" />
              <button type="button" onClick={handleDiscover} disabled={discovering || !form.discovery_url.trim()} className="whitespace-nowrap rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50">
                {discovering ? '发现中...' : '自动发现'}
              </button>
            </div>
          </div>
          <div><label className={labelCls}>Client ID</label><input className={inputCls} value={form.client_id} onChange={e => setForm(f => ({...f, client_id: e.target.value}))} /></div>
          <div><label className={labelCls}>Client Secret {secretSet && <span className="text-xs text-green-600">(已设置)</span>}</label><input className={inputCls} type="password" value={form.client_secret} onChange={e => setForm(f => ({...f, client_secret: e.target.value}))} placeholder={secretSet ? '留空不修改' : '输入密钥'} /></div>
          <div><label className={labelCls}>Authorization Endpoint</label><input className={inputCls} value={form.authorization_endpoint} onChange={e => setForm(f => ({...f, authorization_endpoint: e.target.value}))} /></div>
          <div><label className={labelCls}>Token Endpoint</label><input className={inputCls} value={form.token_endpoint} onChange={e => setForm(f => ({...f, token_endpoint: e.target.value}))} /></div>
          <div><label className={labelCls}>Userinfo Endpoint</label><input className={inputCls} value={form.userinfo_endpoint} onChange={e => setForm(f => ({...f, userinfo_endpoint: e.target.value}))} /></div>
          <div><label className={labelCls}>JWKS URI</label><input className={inputCls} value={form.jwks_uri} onChange={e => setForm(f => ({...f, jwks_uri: e.target.value}))} /></div>
          <div><label className={labelCls}>End Session Endpoint</label><input className={inputCls} value={form.end_session_endpoint} onChange={e => setForm(f => ({...f, end_session_endpoint: e.target.value}))} placeholder="https://authentik.example.com/application/o/app/end-session/" /></div>
          <div><label className={labelCls}>Redirect URI</label>
            <div className="mt-1 flex gap-2">
              <input className="block flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary" value={form.redirect_uri} onChange={e => setForm(f => ({...f, redirect_uri: e.target.value}))} placeholder="例如: https://your-domain/api/auth/sso/callback" />
              <button type="button" onClick={() => setForm(f => ({...f, redirect_uri: `${window.location.origin}/api/auth/sso/callback`}))} className="whitespace-nowrap rounded-md bg-gray-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-700">
                自动填写
              </button>
            </div>
          </div>
          <div><label className={labelCls}>Scopes</label><input className={inputCls} value={form.scopes} onChange={e => setForm(f => ({...f, scopes: e.target.value}))} /></div>
          <div><label className={labelCls}>Groups Claim 字段名</label><input className={inputCls} value={form.groups_claim} onChange={e => setForm(f => ({...f, groups_claim: e.target.value}))} /></div>
        </div>
        <div className="flex items-center gap-3 pt-2">
          <label className="relative inline-flex cursor-pointer items-center">
            <input type="checkbox" checked={form.login_button_enabled} onChange={e => setForm(f => ({...f, login_button_enabled: e.target.checked}))} className="peer sr-only" />
            <div className="h-5 w-9 rounded-full bg-gray-300 after:absolute after:left-[2px] after:top-[2px] after:h-4 after:w-4 after:rounded-full after:bg-white after:transition-all peer-checked:bg-primary peer-checked:after:translate-x-full" />
          </label>
          <span className="text-sm text-gray-700">在登录页显示"统一认证入口"按钮</span>
        </div>
        <div className="flex items-center gap-4 pt-4">
          <button onClick={handleSave} disabled={saving} className="rounded-lg bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
            {saving ? '保存中...' : '保存配置'}
          </button>
          {message && <span className="text-sm">{message}</span>}
        </div>
      </div>
    </div>
  )
}
