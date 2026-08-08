import { useEffect, useState } from 'react'

interface SsoConfig { issuer: string | null; client_id: string | null; client_secret_set: boolean; redirect_uri: string | null; login_button_enabled: boolean; scopes: string; groups_claim: string }

export function SsoConfigPage() {
  const [config, setConfig] = useState<SsoConfig | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/admin/sso-config', { credentials: 'include' })
      .then(r => r.json()).then(setConfig).catch(() => {}).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-6">加载中...</div>
  if (!config) return <div className="p-6">无法加载 SSO 配置</div>

  return (
    <div className="space-y-6 p-6">
      <h2 className="text-xl font-bold">SSO 配置</h2>
      <div className="space-y-4 rounded-lg border p-4">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div><span className="font-medium">Issuer:</span> {config.issuer || '未配置'}</div>
          <div><span className="font-medium">Client ID:</span> {config.client_id || '未配置'}</div>
          <div><span className="font-medium">Client Secret:</span> {config.client_secret_set ? '✅ 已设置' : '❌ 未设置'}</div>
          <div><span className="font-medium">Redirect URI:</span> {config.redirect_uri || '未配置'}</div>
          <div><span className="font-medium">Scopes:</span> {config.scopes}</div>
          <div><span className="font-medium">Groups Claim:</span> {config.groups_claim}</div>
          <div><span className="font-medium">登录页入口:</span> {config.login_button_enabled ? '✅ 已开启' : '❌ 已关闭'}</div>
        </div>
      </div>
    </div>
  )
}
