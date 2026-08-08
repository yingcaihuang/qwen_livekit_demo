# Design Document: SAML Support

## Architecture Overview

本设计在现有 OIDC SSO 架构旁平行新增 SAML 2.0 SP 能力。核心思路：

1. **新增 `saml_service.py`**：封装所有 SAML 协议处理（基于 `python3-saml` 库）
2. **新增 `saml_config` 表**：独立存储 SAML 配置，不污染现有 `sso_config`
3. **新增 API Router `api/saml.py`**：提供 Metadata、Login、ACS、SLO 端点
4. **新增 `saml_login_state` 表**：存储 SP-Initiated 流程的 AuthnRequest ID
5. **复用 `provisioning_service.provision_sso_user`**：SAML 用户开通走相同路径
6. **前端 Tab 化**：SSO 配置页面增加 SAML Tab，登录页扩展多 SSO 入口

### 系统交互流程（SP-Initiated）

```
Browser → LoginPage → GET /api/saml/login
  → saml_service.build_authn_request()
  → Store request_id in saml_login_state
  → 302 Redirect to IdP SSO URL (HTTP-Redirect Binding)

IdP authenticates user → POST /api/saml/acs (SAMLResponse)
  → saml_service.process_response()
    → XML signature verification
    → Conditions validation (time + audience)
    → InResponseTo validation against saml_login_state
  → Extract NameID + attributes
  → provisioning_service.provision_sso_user()
  → auth_service.create_session()
  → Set session cookie → 302 Redirect to RelayState or /
```

### 系统交互流程（IdP-Initiated）

```
IdP portal → POST /api/saml/acs (SAMLResponse, no InResponseTo)
  → saml_service.process_response()
    → Detect missing InResponseTo → skip replay check
    → XML signature verification
    → Conditions validation
  → Extract NameID + attributes
  → provisioning_service.provision_sso_user()
  → auth_service.create_session()
  → Set session cookie → 302 Redirect to RelayState or /
```

### 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| SAML 库 | `python3-saml` (onelogin) | 成熟稳定，API 简洁，内置 XML 安全处理 |
| XML 解析 | `defusedxml` (python3-saml 内置) | 防 XXE 攻击 |
| 数据库 | aiosqlite (现有) | 保持一致性 |
| 前端组件 | shadcn/ui Tabs + Card | 复用现有 UI 体系 |

---

## Components

### Backend Components

#### 1. `app/services/saml_service.py` (新建)

SAML 协议核心服务，封装 `python3-saml` 的调用。

职责：
- 构建 `OneLogin_Saml2_Auth` 实例
- 生成 AuthnRequest（SP-Initiated Login）
- 处理 SAMLResponse（ACS 回调验证）
- 生成 SP Metadata XML
- 解析 IdP Metadata（从 URL 或 XML 内容）
- 构建 LogoutRequest / 处理 LogoutResponse
- RelayState 安全验证

#### 2. `app/api/saml.py` (新建)

SAML 相关的 FastAPI Router，挂载在 `/api/saml` 前缀。

路由：
- `GET /api/saml/metadata` — SP Metadata XML（公开）
- `GET /api/saml/login` — 发起 SP-Initiated 登录
- `POST /api/saml/acs` — Assertion Consumer Service
- `GET /api/saml/slo` — SP-Initiated 登出（redirect to IdP）
- `GET /api/saml/sls` — SLO Service（处理 IdP 发起的 LogoutRequest/Response）

#### 3. `app/api/admin_saml.py` (新建)

SAML 管理配置 API Router，挂载在 `/api/admin/saml-config` 前缀。

路由：
- `GET /api/admin/saml-config` — 获取 SAML 配置（需 `sso:manage`）
- `PUT /api/admin/saml-config` — 保存 SAML 配置（需 `sso:manage`）
- `POST /api/admin/saml-config/parse-metadata` — 解析 IdP Metadata

#### 4. 扩展 `app/api/sso.py`

修改 `public-config` 端点，返回 SAML 启用状态：

```python
@router.get("/public-config")
async def public_config(db: aiosqlite.Connection = Depends(get_db)):
    """Return public SSO config for login page. No auth required."""
    oidc_config = await _load_sso_config(db)
    saml_enabled = await _load_saml_button_enabled(db)
    return {
        "login_button_enabled": oidc_config["login_button_enabled"] if oidc_config else False,
        "saml_login_enabled": saml_enabled,
    }
```

### Frontend Components

#### 5. `SsoConfigPage.tsx` (修改)

将现有页面重构为 Tab 结构：
- **OIDC Tab**：保留现有 OIDC 配置内容
- **SAML Tab**：新增 SAML 配置面板

使用 shadcn/ui `Tabs` 组件实现切换。

#### 6. `SamlConfigPanel.tsx` (新建)

SAML 配置面板组件，包含：
- IdP Metadata URL 输入 + "获取" 按钮
- IdP Metadata XML 手动输入 textarea
- 自动填充的字段：IdP Entity ID、SSO URL、SLO URL、签名证书
- SP Entity ID 配置
- Groups Attribute 名称
- NameID 格式选择（下拉）
- "显示 SAML 入口" 开关
- SP Metadata 端点 URL 展示 + 复制按钮

#### 7. `LoginPage.tsx` (修改)

扩展登录页以支持多 SSO 入口：
- 从 `/api/auth/sso/public-config` 获取 `saml_login_enabled` 字段
- 条件渲染 SAML 登录按钮（链接到 `/api/saml/login`）
- OIDC 和 SAML 按钮并列显示

---

## Interfaces

### API Interfaces

#### `GET /api/saml/metadata`

- Auth: 无需认证
- Response: `application/samlmetadata+xml`
- Body: SAML 2.0 SP Metadata XML

#### `GET /api/saml/login`

- Auth: 无需认证
- Query params: `next` (可选，登录后跳转路径)
- Response: `302 Redirect` to IdP SSO URL
- 行为：生成 AuthnRequest，存储 state，重定向

#### `POST /api/saml/acs`

- Auth: 无需认证（IdP 回调）
- Content-Type: `application/x-www-form-urlencoded`
- Body params: `SAMLResponse` (Base64), `RelayState` (可选)
- Response: `302 Redirect` to RelayState 或 `/`
- Error: `400` with JSON detail

#### `GET /api/saml/slo`

- Auth: 需要有效 session cookie
- Response: `302 Redirect` to IdP SLO URL（如配置了）或清除本地会话后 redirect `/login`

#### `GET /api/saml/sls`

- Auth: 无需认证（IdP 回调）
- Query params: `SAMLRequest` 或 `SAMLResponse`, `RelayState`, `SigAlg`, `Signature`
- Response: `302 Redirect` (LogoutResponse to IdP 或 redirect 到本地登录页)

#### `GET /api/admin/saml-config`

- Auth: 需要 `sso:manage` capability
- Response:
```json
{
  "idp_entity_id": "string | null",
  "idp_sso_url": "string | null",
  "idp_slo_url": "string | null",
  "idp_x509_cert": "string | null",
  "sp_entity_id": "string | null",
  "groups_attribute": "string",
  "nameid_format": "string",
  "sign_algorithm": "string",
  "login_button_enabled": "boolean",
  "idp_metadata_url": "string | null"
}
```

#### `PUT /api/admin/saml-config`

- Auth: 需要 `sso:manage` capability
- Request body:
```json
{
  "idp_entity_id": "string",
  "idp_sso_url": "string",
  "idp_slo_url": "string | null",
  "idp_x509_cert": "string",
  "sp_entity_id": "string | null",
  "groups_attribute": "string",
  "nameid_format": "string",
  "sign_algorithm": "string",
  "login_button_enabled": "boolean",
  "idp_metadata_url": "string | null"
}
```
- Validation: `idp_entity_id`, `idp_sso_url`, `idp_x509_cert` 必填
- Response: 保存后的完整配置 JSON
- Error: `422` 缺少必填字段

#### `POST /api/admin/saml-config/parse-metadata`

- Auth: 需要 `sso:manage` capability
- Request body:
```json
{
  "metadata_url": "string | null",
  "metadata_xml": "string | null"
}
```
- 行为：从 URL 获取或直接解析 XML，提取 IdP 配置字段
- Response:
```json
{
  "idp_entity_id": "string",
  "idp_sso_url": "string",
  "idp_slo_url": "string | null",
  "idp_x509_cert": "string"
}
```
- Error: `400` if URL 不可达或 XML 无效

#### `GET /api/auth/sso/public-config` (修改)

- Auth: 无需认证
- Response (扩展):
```json
{
  "login_button_enabled": true,
  "saml_login_enabled": true
}
```

---

## Data Models

### 新建表 `saml_config`

```sql
CREATE TABLE IF NOT EXISTS saml_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- 单例行
    idp_entity_id TEXT,
    idp_sso_url TEXT,
    idp_slo_url TEXT,
    idp_x509_cert TEXT,                     -- PEM 格式 X.509 证书
    sp_entity_id TEXT,                      -- 默认: {origin}/api/saml/metadata
    groups_attribute TEXT NOT NULL DEFAULT 'groups',
    nameid_format TEXT NOT NULL DEFAULT 'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress',
    sign_algorithm TEXT NOT NULL DEFAULT 'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256',
    login_button_enabled INTEGER NOT NULL DEFAULT 0,
    idp_metadata_url TEXT,
    clock_skew_seconds INTEGER NOT NULL DEFAULT 120,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 新建表 `saml_login_state`

```sql
CREATE TABLE IF NOT EXISTS saml_login_state (
    request_id TEXT PRIMARY KEY,            -- AuthnRequest 的 ID 属性
    relay_state TEXT,                       -- 登录后跳转路径
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

清理策略：每次 ACS 请求处理时，删除 `created_at` 超过 5 分钟的记录。

### 扩展 `users` 表

`auth_source` 字段新增合法值 `'saml'`（现有值为 `'local'` 和 `'sso'`）。

当 SAML 用户通过 `provision_sso_user` 创建时：
- `auth_source` = `'saml'`
- `sso_subject` = NameID 值
- `username` = NameID 或 email（取决于 NameID 格式）

---

## Service Layer Detail

### `saml_service.py` 核心函数

```python
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser

async def load_saml_settings(db: aiosqlite.Connection, request_data: dict) -> dict:
    """从数据库加载 SAML 配置，构建 python3-saml settings dict。"""
    ...

def prepare_request_from_fastapi(request: Request) -> dict:
    """将 FastAPI Request 转换为 python3-saml 所需的 request dict 格式。"""
    return {
        "https": "on" if request.url.scheme == "https" else "off",
        "http_host": request.headers.get("host", ""),
        "script_name": request.url.path,
        "get_data": dict(request.query_params),
        "post_data": {},  # 由调用者填充
    }
```

```python
async def initiate_login(db: aiosqlite.Connection, request: Request, next_url: str | None = None) -> str:
    """
    生成 AuthnRequest 并返回重定向 URL。
    - 存储 request_id 到 saml_login_state
    - 返回 IdP redirect URL（含 SAMLRequest + RelayState）
    """
    ...

async def process_acs(db: aiosqlite.Connection, request: Request, form_data: dict) -> dict:
    """
    处理 ACS POST 回调。
    - 验证签名、时间条件、Audience
    - SP-Initiated: 验证 InResponseTo
    - 返回 {nameid, attributes, session_index, relay_state}
    - 失败时 raise SAMLValidationError
    """
    ...

def generate_sp_metadata(settings: dict) -> str:
    """生成 SP Metadata XML 字符串。"""
    ...

async def parse_idp_metadata(url: str | None = None, xml: str | None = None) -> dict:
    """
    解析 IdP Metadata（从 URL 或 XML 内容）。
    返回 {idp_entity_id, idp_sso_url, idp_slo_url, idp_x509_cert}。
    失败时 raise ValueError。
    """
    ...

def validate_relay_state(relay_state: str | None, allowed_origin: str) -> str | None:
    """
    验证 RelayState 安全性。
    - 允许：相对路径（以 / 开头）或同源 URL
    - 拒绝：外部 URL
    - 返回验证后的路径或 None
    """
    ...

def validate_x509_cert(cert_pem: str) -> bool:
    """验证证书为有效 X.509 PEM 格式且 <= 64KB。"""
    ...
```

### `python3-saml` Settings 结构

```python
def build_saml_settings(config: dict, base_url: str) -> dict:
    """构建 python3-saml 所需的 settings dict。"""
    sp_entity_id = config["sp_entity_id"] or f"{base_url}/api/saml/metadata"
    return {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": sp_entity_id,
            "assertionConsumerService": {
                "url": f"{base_url}/api/saml/acs",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "singleLogoutService": {
                "url": f"{base_url}/api/saml/sls",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "NameIDFormat": config["nameid_format"],
        },
        "idp": {
            "entityId": config["idp_entity_id"],
            "singleSignOnService": {
                "url": config["idp_sso_url"],
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "singleLogoutService": {
                "url": config.get("idp_slo_url", ""),
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": config["idp_x509_cert"],
        },
        "security": {
            "authnRequestsSigned": False,
            "wantAssertionsSigned": True,
            "wantMessagesSigned": False,
            "signatureAlgorithm": config["sign_algorithm"],
            "wantNameId": True,
            "requestedAuthnContext": False,
        },
    }
```

---

## Error Handling

### SAML 验证错误分类

| 错误类型 | HTTP 状态码 | 用户提示 | 日志级别 |
|----------|-------------|----------|----------|
| 签名验证失败 | 400 | "SAML 签名校验失败" | WARNING |
| 时间条件不满足 | 400 | "SAML 断言已过期或尚未生效" | WARNING |
| Audience 不匹配 | 400 | "SAML Audience 校验失败" | WARNING |
| InResponseTo 不匹配 | 400 | "SAML 请求匹配失败（可能重放）" | WARNING |
| AuthnRequest ID 已过期 | 400 | "登录请求已超时，请重新登录" | INFO |
| IdP Metadata 解析失败 | 400 | "IdP Metadata 格式无效" | ERROR |
| IdP Metadata URL 不可达 | 400 | "无法访问 IdP Metadata URL" | ERROR |
| 配置缺少必填字段 | 422 | 具体字段名 | INFO |
| 权限不足 | 403 | "权限不足" | INFO |
| SAML 未启用 | 403 | "SAML 登录入口未启用" | INFO |
| XML 包含 DTD/外部实体 | 400 | "不安全的 XML 内容" | WARNING |
| RelayState 外部 URL | 400 | (静默忽略，跳转到 /) | WARNING |
| X.509 证书格式无效 | 422 | "证书格式无效" | INFO |

### 自定义异常

```python
class SAMLValidationError(Exception):
    """SAML 验证流程中的错误。"""
    def __init__(self, message: str, error_code: str):
        self.message = message
        self.error_code = error_code
        super().__init__(message)
```

### 日志安全

所有 SAML 日志记录遵循以下原则：
- **记录**：NameID、操作类型、错误代码、时间戳、客户端 IP
- **不记录**：完整 SAML Assertion XML、用户属性值、证书内容

---

## Security Considerations

### XML 安全
- `python3-saml` 内部使用 `defusedxml` 或 `lxml` 安全模式解析 XML
- 额外检测：在将 XML 传入 python3-saml 前，预检是否含 `<!DOCTYPE` 或 `<!ENTITY`
- Canonicalization (C14N) 由 python3-saml 自动处理

### 防重放
- `saml_login_state` 表中的 `request_id` 为唯一约束
- ACS 处理成功后立即删除对应记录
- 5 分钟 TTL 过期自动清理

### RelayState 验证
- 仅接受以 `/` 开头的相对路径
- 或以配置的 `base_url` 开头的完整 URL
- 拒绝 `//`, `javascript:`, `data:` 等协议

### 证书验证
- 存储前验证为合法 X.509 PEM 格式
- 大小上限 64KB
- 使用 `cryptography` 库解析验证

---

## File Structure

```
azure-voice-admin/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── saml.py              (新建 - SAML 公开端点)
│   │   │   ├── admin_saml.py        (新建 - SAML 管理接口)
│   │   │   └── sso.py               (修改 - 扩展 public-config)
│   │   ├── services/
│   │   │   └── saml_service.py      (新建 - SAML 协议核心)
│   │   └── schema.sql               (修改 - 新增两表)
│   ├── requirements.txt             (修改 - 添加 python3-saml)
│   └── tests/
│       ├── test_saml_service.py     (新建)
│       └── test_saml_api.py         (新建)
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── LoginPage.tsx        (修改 - 多 SSO 入口)
│       │   └── admin/
│       │       └── SsoConfigPage.tsx (修改 - Tab 化 + SAML panel)
│       └── components/
│           └── admin/
│               └── SamlConfigPanel.tsx (新建)
```

---

## Dependencies

### Python (新增)

```
python3-saml>=1.16.0
```

`python3-saml` 依赖：
- `xmlsec` (C 扩展，需要系统 `xmlsec1` 库)
- `lxml`
- `isodate`

### 系统依赖

```bash
# Debian/Ubuntu
apt-get install -y xmlsec1 libxmlsec1-dev libxmlsec1-openssl

# macOS
brew install libxmlsec1
```

---

## Provisioning Integration

SAML 用户开通复用现有 `provision_sso_user` 函数。调用方式：

```python
from app.services.provisioning_service import provision_sso_user

# 从 SAML Assertion 中提取信息后
user_id = await provision_sso_user(
    db,
    subject=nameid_value,           # NameID
    username=email or nameid_value,  # 优先使用 email
    email=email_attribute,           # AttributeStatement 中的 email
    groups=groups_list,              # 按 groups_attribute 配置提取
)
```

`provision_sso_user` 已内置：
- 首次登录自动创建账号
- 重复登录更新 email/username
- 基于 `group_role_mappings` 计算角色
- 尊重 `role_override` 标记
- 无匹配组时默认 `viewer` 角色

**注意**：`auth_source` 字段值需区分 SAML 用户。修改 `provision_sso_user` 增加可选参数 `auth_source: str = 'sso'`，SAML 调用时传入 `'saml'`。

---

## Login Page Multi-SSO Logic

```typescript
// LoginPage.tsx - 扩展后的 SSO 状态
interface SsoPublicConfig {
  login_button_enabled: boolean  // OIDC
  saml_login_enabled: boolean    // SAML
}

// 渲染逻辑
// 1. 如果 login_button_enabled: 显示 OIDC 按钮 (href="/api/auth/sso/login")
// 2. 如果 saml_login_enabled: 显示 SAML 按钮 (href="/api/saml/login")
// 3. 两者都启用时，并列显示（分隔线 "或"）
// 4. 都不启用时，仅显示本地登录表单
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

<!--
Acceptance Criteria Testing Prework:

1.1. THE Auth_System SHALL 在数据库中维护 SAML_Config 字段
  Thoughts: This is a structural requirement about database schema. There's no varying input to test.
  Classification: SMOKE
  Test Strategy: Verify table exists with expected columns.

1.2. THE Auth_System SHALL 支持 IdP Metadata URL 或 XML 两种方式导入
  Thoughts: This describes two input methods for the same parsing function. Behavior varies with the XML content.
  Classification: EXAMPLE
  Test Strategy: Test both URL and direct XML paths with representative metadata.

1.3. WHEN 管理员提供 IdP Metadata URL → 解析出字段
  Thoughts: This is about fetching and parsing. The parsing logic varies with XML structure. Fetching is I/O.
  Classification: INTEGRATION (fetch) + PROPERTY (parse logic)
  Test Strategy: Mock HTTP, test parsing logic with varied valid metadata XMLs.

1.4. WHEN 管理员直接上传 IdP Metadata XML → 解析字段
  Thoughts: Pure parsing. Input varies significantly (different IdPs produce different metadata). Can generate random valid SAML metadata and verify extraction.
  Classification: PROPERTY
  Test Strategy: For any valid SAML metadata XML containing required elements, parsing should extract all fields correctly.

1.5. IF IdP Metadata URL 不可达或返回无效 XML → 错误
  Thoughts: Error handling for specific invalid inputs. Edge case testing.
  Classification: EDGE_CASE
  Test Strategy: Test with unreachable URL and various invalid XMLs.

1.6. IF IdP Metadata XML 缺少必要字段 → 校验错误
  Thoughts: Validation logic. For any metadata XML missing SSO binding or cert, should reject.
  Classification: PROPERTY
  Test Strategy: For any metadata XML that is missing required elements, parser should raise error.

2.1-2.5. SP Metadata endpoint
  Thoughts: These describe what the generated SP Metadata XML should contain. We can test that for any valid SAML config, the generated metadata always contains required elements.
  Classification: PROPERTY (2.2, 2.3, 2.4) / EXAMPLE (2.1, 2.5)
  Test Strategy: For any valid saml_config, generated SP metadata must be valid XML and contain required elements.

3.1-3.2. AuthnRequest generation + state storage
  Thoughts: For any SAML config, the generated AuthnRequest must contain a unique ID and ACS URL. The ID must be stored in state table.
  Classification: PROPERTY
  Test Strategy: For any valid SAML config, generated AuthnRequest contains unique ID and correct ACS URL.

3.3. HTTP-Redirect Binding encoding
  Thoughts: Round-trip property. Deflate+Base64 encoding should be reversible.
  Classification: PROPERTY
  Test Strategy: For any AuthnRequest XML, deflate+base64 encode then decode should produce the original.

3.4. RelayState in AuthnRequest
  Thoughts: Simple parameter passing. Example-based.
  Classification: EXAMPLE

3.5. AuthnRequest signing
  Thoughts: Conditional behavior based on config. Example-based.
  Classification: EXAMPLE

4.1. ACS endpoint exists
  Thoughts: Structural. Smoke test.
  Classification: SMOKE

4.2-4.3. XML signature verification
  Thoughts: Core security property. For any SAMLResponse signed with a non-matching key, verification must fail.
  Classification: PROPERTY
  Test Strategy: For any SAMLResponse, verification with correct cert succeeds; with wrong cert fails.

4.4-4.5. Conditions validation (time + audience)
  Thoughts: For any assertion with expired time or wrong audience, must reject.
  Classification: PROPERTY
  Test Strategy: For any assertion where current time is outside NotBefore/NotOnOrAfter, validation fails.

4.6-4.8. InResponseTo validation + replay prevention
  Thoughts: For any consumed request_id, a second attempt with same ID must be rejected. This is an idempotence/replay property.
  Classification: PROPERTY
  Test Strategy: For any request_id, consuming it once succeeds; consuming it again fails.

4.9. Clock skew tolerance
  Thoughts: Edge case around time boundaries. Example-based.
  Classification: EDGE_CASE

5.1-5.6. IdP-Initiated flow
  Thoughts: 5.1 is a classification property (no InResponseTo → IdP-Initiated). 5.5 is about RelayState redirect.
  Classification: PROPERTY (5.1) / EXAMPLE (others)

6.1-6.8. User provisioning
  Thoughts: 6.4-6.5 are the core properties about role computation. Already tested by provision_sso_user. 6.6 about re-login updating roles is a property.
  Classification: PROPERTY (6.4, 6.5, 6.6)
  Test Strategy: These are already covered by provisioning_service tests. For SAML specifically, we test that attributes are correctly extracted and passed.

7.1-7.7. Login page SSO buttons
  Thoughts: UI rendering logic based on config flags. Can be property-tested: for any combination of (oidc_enabled, saml_enabled), correct buttons shown.
  Classification: PROPERTY (7.1-7.6 as combined logic)
  Test Strategy: For any boolean combination of OIDC/SAML enabled flags, login page renders correct set of buttons.

8.1-8.7. Admin config panel
  Thoughts: 8.4-8.5 (validation) is property-testable. 8.7 (auth check) is example-based.
  Classification: PROPERTY (8.4-8.5) / EXAMPLE (others)
  Test Strategy: For any config submission missing required fields, must be rejected.

9.1-9.5. Logout
  Thoughts: 9.1 is always true (local invalidation). Integration behavior for SLO.
  Classification: EXAMPLE / INTEGRATION

10.1. Canonicalization - handled by library
  Classification: INTEGRATION

10.2. XXE prevention
  Thoughts: For any XML containing DTD declarations, must be rejected.
  Classification: PROPERTY
  Test Strategy: For any SAML XML containing <!DOCTYPE or <!ENTITY, processing must fail.

10.3. Replay prevention - covered by 4.6-4.8
  Classification: PROPERTY (already counted above)

10.4. X.509 certificate validation
  Thoughts: For any string, validate_x509_cert returns true only if it's valid PEM and <= 64KB.
  Classification: PROPERTY
  Test Strategy: For any valid X.509 PEM cert <= 64KB, validation passes. For invalid strings, fails.

10.5. RelayState validation
  Thoughts: For any URL/path, validate_relay_state accepts only relative paths or same-origin URLs.
  Classification: PROPERTY
  Test Strategy: For any string, if it starts with / (no //) it's accepted. External URLs rejected.

10.6. Log safety - not testable as property
  Classification: EXAMPLE

11.1-11.7. IdP compatibility
  Thoughts: Integration testing with different IdP metadata formats.
  Classification: INTEGRATION

Property Reflection:
- 4.2-4.3 (signature verification) and 5.2 (IdP-Initiated also verifies) are the same underlying property
- 4.6-4.8 (replay) and 10.3 (replay) are the same property
- 1.4 (parse metadata) and 1.6 (reject invalid) are complementary: combine into "metadata parsing correctness"
- 6.4+6.5 are already covered by existing provisioning_service tests; focus on SAML-specific attribute extraction
- 7.1-7.6 can be combined into one property about SSO button visibility logic

Final consolidated properties:
1. IdP Metadata parsing round-trip (valid metadata → correct field extraction)
2. Invalid metadata rejection (missing fields → error)
3. SP Metadata generation completeness (config → valid metadata XML)
4. AuthnRequest encoding round-trip (deflate+base64)
5. SAML Response signature verification (wrong cert → reject)
6. Assertion time conditions enforcement
7. InResponseTo replay prevention (consume once only)
8. RelayState validation (reject external URLs)
9. X.509 certificate format validation
10. XXE rejection
11. SAML config required field validation
12. Login page SSO button visibility logic
-->


### Property 1: IdP Metadata Parsing Extracts Required Fields

*For any* valid SAML 2.0 IdP Metadata XML that contains an `IDPSSODescriptor` with at least one `SingleSignOnService` (HTTP-Redirect binding) and one `KeyDescriptor` with an X.509 certificate, parsing that metadata SHALL produce a result containing a non-empty `idp_entity_id`, `idp_sso_url`, and `idp_x509_cert`.

**Validates: Requirements 1.3, 1.4**

### Property 2: Invalid Metadata Rejection

*For any* XML string that is either not valid XML, or valid XML that lacks an `IDPSSODescriptor`, or lacks a `SingleSignOnService` element with HTTP-Redirect binding, or lacks a `KeyDescriptor` with an X.509 certificate, the metadata parser SHALL raise an error and not return a partial result.

**Validates: Requirements 1.5, 1.6**

### Property 3: SP Metadata Generation Completeness

*For any* valid `saml_config` record (with non-empty `idp_entity_id`, `idp_sso_url`, `idp_x509_cert`, and `sp_entity_id`), the generated SP Metadata XML SHALL be well-formed XML conforming to the SAML 2.0 Metadata schema and SHALL contain an `EntityDescriptor` with the configured SP Entity ID, an `AssertionConsumerService` element with HTTP-POST binding, and a `SingleLogoutService` element with HTTP-Redirect binding.

**Validates: Requirements 2.2, 2.3, 2.4**

### Property 4: AuthnRequest SAMLRequest Encoding Round-Trip

*For any* valid AuthnRequest XML string, applying Deflate compression followed by Base64 encoding, and then applying Base64 decoding followed by Inflate decompression, SHALL produce a byte sequence identical to the original XML bytes.

**Validates: Requirements 3.3**

### Property 5: Signature Verification Rejects Invalid Signatures

*For any* SAML Response XML that is signed with a private key whose corresponding certificate does NOT match the `idp_x509_cert` stored in `saml_config`, the ACS validation process SHALL reject the response and return a signature verification failure error.

**Validates: Requirements 4.2, 4.3, 5.2, 5.3**

### Property 6: Assertion Time Conditions Enforcement

*For any* SAML Assertion where the current system time (accounting for the configured `clock_skew_seconds`) falls outside the `NotBefore` to `NotOnOrAfter` window, the ACS validation process SHALL reject the assertion with a time condition failure error.

**Validates: Requirements 4.4, 4.5, 4.9**

### Property 7: InResponseTo Single-Use Consumption

*For any* `request_id` stored in `saml_login_state`, processing a valid SAMLResponse with `InResponseTo` matching that `request_id` SHALL succeed on the first attempt and SHALL fail on any subsequent attempt with the same `request_id`, regardless of how quickly the second attempt follows.

**Validates: Requirements 4.6, 4.7, 4.8, 10.3**

### Property 8: RelayState Rejects External URLs

*For any* string that does not start with a single `/` character (excluding `//`), or starts with a scheme other than the configured origin, or contains `javascript:`, `data:`, or `vbscript:` protocols, `validate_relay_state` SHALL return `None` (rejected). Conversely, *for any* string that is a relative path starting with `/` (and not `//`), `validate_relay_state` SHALL return that path unchanged.

**Validates: Requirements 5.5, 10.5**

### Property 9: X.509 Certificate Validation

*For any* string input, `validate_x509_cert` SHALL return `True` if and only if the string is a valid PEM-encoded X.509 certificate and its byte length does not exceed 65536 bytes. For any string that is not valid PEM, not a valid X.509 structure, or exceeds 64KB, it SHALL return `False`.

**Validates: Requirements 10.4**

### Property 10: XXE Rejection

*For any* XML string that contains a `<!DOCTYPE` declaration or an `<!ENTITY` reference (external or internal), the SAML XML processing pipeline SHALL reject the input before any parsing or signature verification occurs, preventing XML External Entity attacks.

**Validates: Requirements 10.2**

### Property 11: SAML Config Required Field Validation

*For any* SAML config submission where `idp_entity_id` is empty/null, or `idp_sso_url` is empty/null, or `idp_x509_cert` is empty/null, the save operation SHALL be rejected with a validation error indicating the specific missing field(s). Conversely, *for any* submission where all three required fields are non-empty, validation SHALL pass (assuming values are well-formed).

**Validates: Requirements 8.4, 8.5**

### Property 12: Login Page SSO Button Visibility

*For any* combination of boolean values `(oidc_enabled, saml_enabled)`, the login page SHALL render OIDC button if and only if `oidc_enabled` is true, and SHALL render SAML button if and only if `saml_enabled` is true. When both are false, only the local login form SHALL be visible. The buttons SHALL be independent — enabling one does not affect the other.

**Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6**
