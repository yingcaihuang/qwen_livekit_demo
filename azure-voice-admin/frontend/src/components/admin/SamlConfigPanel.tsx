import { useEffect, useState } from 'react'
import { Shield, Copy, Check, ChevronRight } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { toast } from '@/components/ui/toast'

interface SamlConfig {
  idp_entity_id: string
  idp_sso_url: string
  idp_slo_url: string
  idp_x509_cert: string
  sp_entity_id: string
  groups_attribute: string
  nameid_format: string
  sign_algorithm: string
  login_button_enabled: boolean
  idp_metadata_url: string
}

const NAMEID_FORMAT_OPTIONS = [
  { value: 'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress', label: 'Email' },
  { value: 'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent', label: 'Persistent' },
  { value: 'urn:oasis:names:tc:SAML:2.0:nameid-format:unspecified', label: 'Unspecified' },
]

const DEFAULT_FORM: SamlConfig = {
  idp_entity_id: '',
  idp_sso_url: '',
  idp_slo_url: '',
  idp_x509_cert: '',
  sp_entity_id: '',
  groups_attribute: 'groups',
  nameid_format: 'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress',
  sign_algorithm: 'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256',
  login_button_enabled: false,
  idp_metadata_url: '',
}

export function SamlConfigPanel() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [fetching, setFetching] = useState(false)
  const [message, setMessage] = useState('')
  const [form, setForm] = useState<SamlConfig>(DEFAULT_FORM)
  const [metadataXml, setMetadataXml] = useState('')
  const [copiedField, setCopiedField] = useState<string | null>(null)

  const spMetadataUrl = `${window.location.origin}/api/saml/metadata`

  useEffect(() => {
    fetch('/api/admin/saml-config', { credentials: 'include' })
      .then((r) => r.json())
      .then((d) => {
        setForm({
          idp_entity_id: d.idp_entity_id || '',
          idp_sso_url: d.idp_sso_url || '',
          idp_slo_url: d.idp_slo_url || '',
          idp_x509_cert: d.idp_x509_cert || '',
          sp_entity_id: d.sp_entity_id || '',
          groups_attribute: d.groups_attribute || 'groups',
          nameid_format: d.nameid_format || DEFAULT_FORM.nameid_format,
          sign_algorithm: d.sign_algorithm || DEFAULT_FORM.sign_algorithm,
          login_button_enabled: d.login_button_enabled ?? false,
          idp_metadata_url: d.idp_metadata_url || '',
        })
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleFetchMetadata = async () => {
    const url = form.idp_metadata_url.trim()
    const xml = metadataXml.trim()
    if (!url && !xml) return

    setFetching(true)
    setMessage('')
    try {
      const res = await fetch('/api/admin/saml-config/parse-metadata', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          metadata_url: url || null,
          metadata_xml: xml || null,
        }),
      })
      if (res.ok) {
        const d = await res.json()
        setForm((f) => ({
          ...f,
          idp_entity_id: d.idp_entity_id || f.idp_entity_id,
          idp_sso_url: d.idp_sso_url || f.idp_sso_url,
          idp_slo_url: d.idp_slo_url || f.idp_slo_url,
          idp_x509_cert: d.idp_x509_cert || f.idp_x509_cert,
        }))
        setMessage('✅ IdP 信息已自动填充，请检查后保存')
      } else {
        const d = await res.json().catch(() => ({}))
        setMessage(`❌ ${d.detail || '解析 IdP Metadata 失败'}`)
      }
    } catch {
      setMessage('❌ 网络错误')
    } finally {
      setFetching(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setMessage('')
    try {
      const res = await fetch('/api/admin/saml-config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(form),
      })
      if (res.ok) {
        setMessage('✅ SAML 配置已保存')
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

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-muted-foreground">加载中...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Authentik SAML 配置指南 */}
      <Card className="border-amber-200 bg-amber-50/50">
        <CardContent className="p-0">
          <details className="group">
            <summary className="flex cursor-pointer items-center gap-2 px-6 py-4 text-sm font-semibold text-amber-800 hover:bg-amber-100/50 [&::-webkit-details-marker]:hidden list-none">
              <ChevronRight className="h-4 w-4 transition-transform group-open:rotate-90" />
              📖 Authentik SAML 配置指南（点击展开）
            </summary>
            <div className="border-t border-amber-200 px-6 py-4 space-y-5 text-sm">
              {/* Step 1 */}
              <div className="space-y-2">
                <h4 className="font-semibold text-amber-900">第一步：在 Authentik 创建 SAML Provider</h4>
                <ol className="list-decimal pl-5 space-y-1 text-xs text-amber-800">
                  <li>登录 Authentik 管理后台</li>
                  <li>进入 <strong>Applications → Providers → Create → SAML Provider</strong></li>
                  <li>填写关键字段：</li>
                </ol>
                <div className="ml-5 rounded-md border border-amber-200 bg-white p-3 text-xs space-y-1">
                  <div className="flex gap-2"><span className="w-44 shrink-0 font-medium text-amber-700">ACS URL:</span><code className="text-foreground">{window.location.origin}/api/saml/acs</code></div>
                  <div className="flex gap-2"><span className="w-44 shrink-0 font-medium text-amber-700">Issuer / Audience:</span><code className="text-foreground">{window.location.origin}/api/saml/metadata</code></div>
                  <div className="flex gap-2"><span className="w-44 shrink-0 font-medium text-amber-700">SP Binding:</span><code className="text-foreground">Post</code></div>
                  <div className="flex gap-2"><span className="w-44 shrink-0 font-medium text-amber-700">NameID Mapping:</span><code className="text-foreground">authentik default SAML Mapping: Email</code></div>
                  <div className="flex gap-2"><span className="w-44 shrink-0 font-medium text-amber-700">Signing Certificate:</span><code className="text-foreground">选择 Authentik 自带的自签名证书</code></div>
                </div>
                <p className="ml-5 text-xs text-amber-700 italic">点击 Finish 保存</p>
              </div>

              {/* Step 2 */}
              <div className="space-y-2">
                <h4 className="font-semibold text-amber-900">第二步：创建 Application</h4>
                <ol className="list-decimal pl-5 space-y-1 text-xs text-amber-800">
                  <li>进入 <strong>Applications → Applications → Create</strong></li>
                  <li>Name 填写应用名称（如 <code>Azure Voice Admin</code>）</li>
                  <li>Provider 选择刚才创建的 SAML Provider</li>
                  <li>保存</li>
                </ol>
              </div>

              {/* Step 3 */}
              <div className="space-y-2">
                <h4 className="font-semibold text-amber-900">第三步：配置 Groups 属性映射（推荐）</h4>
                <ol className="list-decimal pl-5 space-y-1 text-xs text-amber-800">
                  <li>进入 <strong>Customization → Property Mappings → Create → SAML Property Mapping</strong></li>
                  <li>Name: <code>SAML Groups</code></li>
                  <li>SAML Attribute Name: <code>groups</code></li>
                  <li>Expression:</li>
                </ol>
                <div className="ml-5 rounded-md border border-amber-200 bg-white p-2">
                  <code className="text-xs text-foreground">return [group.name for group in request.user.ak_groups.all()]</code>
                </div>
                <p className="ml-5 text-xs text-amber-700">保存后，回到 SAML Provider 编辑页，在 Property Mappings 中勾选此映射</p>
              </div>

              {/* Step 4 */}
              <div className="space-y-2">
                <h4 className="font-semibold text-amber-900">第四步：回到本页面配置</h4>
                <ol className="list-decimal pl-5 space-y-1 text-xs text-amber-800">
                  <li>
                    在下方 <strong>IdP Metadata URL</strong> 中填入：
                    <code className="ml-1 rounded bg-white px-1.5 py-0.5 border text-xs">
                      https://你的authentik域名/application/saml/你的应用slug/metadata/
                    </code>
                  </li>
                  <li>点击 <strong>"获取"</strong> 按钮，系统自动填充 IdP 信息</li>
                  <li>确认 <strong>Groups Attribute</strong> 为 <code>groups</code></li>
                  <li>打开 <strong>"在登录页显示 SAML 入口"</strong> 开关</li>
                  <li>点击 <strong>"保存配置"</strong></li>
                </ol>
              </div>

              {/* Step 5 */}
              <div className="space-y-2">
                <h4 className="font-semibold text-amber-900">第五步：验证</h4>
                <ol className="list-decimal pl-5 space-y-1 text-xs text-amber-800">
                  <li>访问登录页，确认出现 <strong>"SAML 企业登录"</strong> 按钮</li>
                  <li>点击按钮跳转到 Authentik 登录</li>
                  <li>登录完成后自动跳回本平台</li>
                </ol>
              </div>

              {/* Troubleshooting */}
              <div className="space-y-2 rounded-md border border-amber-300 bg-amber-100/50 p-3">
                <h4 className="font-semibold text-amber-900">⚠️ 常见问题</h4>
                <ul className="list-disc pl-5 space-y-1 text-xs text-amber-800">
                  <li><strong>签名验证失败：</strong>确保证书是 Provider 使用的签名证书的完整 PEM 内容</li>
                  <li><strong>Audience 不匹配：</strong>Authentik Provider 的 Audience 字段需与本页 SP Entity ID 完全一致</li>
                  <li><strong>用户无角色：</strong>需在「角色管理 → 组映射」中配置 Authentik 组名到平台角色的映射</li>
                </ul>
              </div>
            </div>
          </details>
        </CardContent>
      </Card>

      {/* Section 1: IdP Metadata Import */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Shield className="h-5 w-5 text-indigo-500" />
            IdP Metadata 导入
          </CardTitle>
          <CardDescription>通过 URL 自动获取或手动粘贴 IdP Metadata XML</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>IdP Metadata URL</Label>
            <div className="flex gap-2">
              <Input
                className="flex-1"
                value={form.idp_metadata_url}
                onChange={(e) => setForm((f) => ({ ...f, idp_metadata_url: e.target.value }))}
                placeholder="https://idp.example.com/metadata"
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={handleFetchMetadata}
                disabled={fetching || (!form.idp_metadata_url.trim() && !metadataXml.trim())}
                className="shrink-0"
              >
                {fetching ? '获取中...' : '获取'}
              </Button>
            </div>
          </div>
          <div className="space-y-2">
            <Label>IdP Metadata XML <span className="text-xs font-normal text-muted-foreground">(手动输入)</span></Label>
            <textarea
              className="flex min-h-[120px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              value={metadataXml}
              onChange={(e) => setMetadataXml(e.target.value)}
              placeholder="粘贴 IdP Metadata XML 内容..."
            />
          </div>
        </CardContent>
      </Card>

      {/* Section 2: IdP Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">IdP 配置</CardTitle>
          <CardDescription>IdP 连接参数（可通过 Metadata 自动填充）</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>IdP Entity ID <span className="text-xs text-destructive">*</span></Label>
              <Input
                value={form.idp_entity_id}
                onChange={(e) => setForm((f) => ({ ...f, idp_entity_id: e.target.value }))}
                placeholder="https://idp.example.com/entity"
              />
            </div>
            <div className="space-y-2">
              <Label>IdP SSO URL <span className="text-xs text-destructive">*</span></Label>
              <Input
                value={form.idp_sso_url}
                onChange={(e) => setForm((f) => ({ ...f, idp_sso_url: e.target.value }))}
                placeholder="https://idp.example.com/sso"
              />
            </div>
            <div className="space-y-2">
              <Label>IdP SLO URL <span className="text-xs font-normal text-muted-foreground">(可选)</span></Label>
              <Input
                value={form.idp_slo_url}
                onChange={(e) => setForm((f) => ({ ...f, idp_slo_url: e.target.value }))}
                placeholder="https://idp.example.com/slo"
              />
            </div>
            <div className="space-y-2">
              <Label>SP Entity ID <span className="text-xs font-normal text-muted-foreground">(留空使用默认值)</span></Label>
              <Input
                value={form.sp_entity_id}
                onChange={(e) => setForm((f) => ({ ...f, sp_entity_id: e.target.value }))}
                placeholder={spMetadataUrl}
              />
            </div>
          </div>
          <div className="mt-4 space-y-2">
            <Label>IdP 签名证书 (X.509 PEM) <span className="text-xs text-destructive">*</span></Label>
            <textarea
              className="flex min-h-[100px] w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-xs shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              value={form.idp_x509_cert}
              onChange={(e) => setForm((f) => ({ ...f, idp_x509_cert: e.target.value }))}
              placeholder="-----BEGIN CERTIFICATE-----&#10;MIIx...&#10;-----END CERTIFICATE-----"
            />
          </div>
        </CardContent>
      </Card>

      {/* Section 3: SP Options */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">SP 选项</CardTitle>
          <CardDescription>属性映射、NameID 格式与登录入口配置</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Groups Attribute 名称</Label>
              <Input
                value={form.groups_attribute}
                onChange={(e) => setForm((f) => ({ ...f, groups_attribute: e.target.value }))}
                placeholder="groups"
              />
              <p className="text-xs text-muted-foreground">
                SAML Assertion 中表示用户组的属性名称
              </p>
            </div>
            <div className="space-y-2">
              <Label>NameID 格式</Label>
              <select
                value={form.nameid_format}
                onChange={(e) => setForm((f) => ({ ...f, nameid_format: e.target.value }))}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {NAMEID_FORMAT_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
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
              <span className="text-sm text-foreground">在登录页显示"SAML 登录"按钮</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Section 4: SP Metadata Endpoint */}
      <Card className="border-blue-200 bg-blue-50/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold text-blue-800">
            📋 SP Metadata 端点
          </CardTitle>
          <CardDescription className="text-xs text-blue-700">
            将以下 URL 提供给 IdP 管理员，用于导入 SP 信任关系
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3">
            <span className="w-40 shrink-0 text-xs font-medium text-blue-700">SP Metadata URL:</span>
            <code className="flex-1 rounded-md border bg-white px-3 py-1.5 text-xs text-foreground">
              {spMetadataUrl}
            </code>
            <Button
              variant="ghost"
              size="sm"
              className="shrink-0 text-blue-600"
              onClick={() => copyToClipboard(spMetadataUrl, 'metadata')}
            >
              {copiedField === 'metadata' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
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
