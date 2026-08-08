# Design Document
## Overview
本设计为 Azure OpenAI 测试平台新增用户鉴权与授权系统。系统在现有 FastAPI + aiosqlite 后端与 React + TypeScript + Vite + Tailwind v4 前端（同源部署，Caddy 提供前端静态资源、反代后端）之上，引入：

- 两条并存登录路径：本地账号（bcrypt/argon2 哈希，用于超级管理员与应急登录）与 Authentik OIDC（授权码 + PKCE，首登自动开通）。
- 服务端会话（session token 存 SQLite，凭据经 httpOnly + Secure + SameSite Cookie 下发）。
- 四级 RBAC（super_admin / admin / tester / viewer）与细粒度能力（capability），后端接口用依赖注入式 `require_permission(...)` 守卫，前端用受保护路由组件与能力驱动的导航显隐。
- 资源多租户隔离：所有资源（实例、对话、图片、语音会话）记录归属用户，普通用户仅可见/操作自己的资源，admin/super_admin 可查看全部（`resource:read:all` 能力）。
- 组→角色映射表、SSO 配置管理后台（client_secret 对称加密存储、脱敏返回、首页入口开关）、用户管理后台。
- 安全加固：收紧 CORS、CSRF 防护、登录限流、敏感字段加密、日志脱敏。

设计遵循现有代码约定：新增表通过 `schema.sql`（`CREATE TABLE IF NOT EXISTS`）+ `database.py::_migrate()`（幂等 `ALTER`/播种）落地，并配套 `tests/` 中的迁移测试；后端按 `app/api/*.py` 路由 + `app/services/*.py` 服务 + `app/models/*.py` Pydantic 模型分层；前端沿用 `pages/`、`components/`、`hooks/` 结构与 Radix/shadcn 组件。

## Architecture
### 组件总览

```
浏览器 (React SPA)
  ├─ LoginPage（本地表单 + 条件显隐的 SSO 按钮）
  ├─ AuthProvider（会话上下文：user / roles / capabilities）
  ├─ ProtectedRoute（能力驱动的路由守卫）
  └─ 管理后台页面（用户 / 组映射 / SSO 配置）
        │  fetch(credentials: 'include')  同源
        ▼
Caddy（同源反向代理，转发 /api /ws，其余回退 index.html）
        ▼
FastAPI 后端
  ├─ AuthMiddleware / 依赖：get_current_user、require_permission(cap)
  ├─ app/api/auth.py        登录 / 登出 / 当前用户 / 改密
  ├─ app/api/sso.py         SSO 发起 / 回调（OIDC + PKCE）
  ├─ app/api/admin_users.py 用户管理（user:manage）
  ├─ app/api/admin_roles.py 组→角色映射（role:manage）
  ├─ app/api/admin_sso.py   SSO 配置管理（sso:manage）
  ├─ services/auth_service.py       本地认证、会话签发/校验、限流
  ├─ services/oidc_service.py       discovery / 换 token / 验签 / userinfo
  ├─ services/provisioning_service.py  SSO 自动开通 + 角色计算
  ├─ services/crypto_service.py     对称加密（client_secret 等）
  └─ services/rbac.py               角色→能力映射、能力并集计算
        ▼
SQLite（新增表：users, user_roles, group_role_mappings, sso_config, auth_sessions, login_attempts）
        ▼
Authentik（OIDC IdP：authorize / token / userinfo / jwks / discovery）
```

### 请求鉴权流程（受保护接口）

1. 前端以 `credentials: 'include'` 发起请求，浏览器自动携带 Session_Cookie。
2. FastAPI 依赖 `get_current_user` 解析 Cookie 中的 session token，查 `auth_sessions` 校验存在且未过期，加载用户与角色。
3. `require_permission(cap)` 依赖计算用户能力并集，判断是否包含 `cap`；不含则抛 403。
4. 未携带有效会话访问受保护接口抛 401（登录、SSO 回调、`/api/health` 例外）。

## Data Models
### 新增表结构（追加到 `app/schema.sql`，均用 `IF NOT EXISTS`）

```sql
-- 用户（本地账号与 SSO 账号统一存储）
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    username TEXT NOT NULL UNIQUE,        -- 本地登录名 / SSO 稳定标识（sub 或 preferred_username）
    email TEXT,
    auth_source TEXT NOT NULL DEFAULT 'local',  -- 'local' | 'sso'
    password_hash TEXT,                   -- 仅本地账号；SSO 账号为 NULL
    sso_subject TEXT UNIQUE,              -- OIDC sub；本地账号为 NULL
    is_active INTEGER NOT NULL DEFAULT 1, -- 0 表示禁用
    must_change_password INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 用户→角色（多对多；四级角色以字符串存储，取值受应用层校验约束）
CREATE TABLE IF NOT EXISTS user_roles (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                   -- 'super_admin'|'admin'|'tester'|'viewer'
    PRIMARY KEY (user_id, role)
);

-- Authentik 组名 → 平台角色 映射
CREATE TABLE IF NOT EXISTS group_role_mappings (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    group_name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,                   -- 四个合法角色之一（应用层校验）
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- SSO 配置（单行有效；client_secret 密文存储）
CREATE TABLE IF NOT EXISTS sso_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- 单例行
    issuer TEXT,
    discovery_url TEXT,
    client_id TEXT,
    client_secret_encrypted TEXT,         -- 对称加密后的密文，绝不明文
    authorization_endpoint TEXT,
    token_endpoint TEXT,
    userinfo_endpoint TEXT,
    jwks_uri TEXT,
    redirect_uri TEXT,
    scopes TEXT NOT NULL DEFAULT 'openid profile email groups',
    groups_claim TEXT NOT NULL DEFAULT 'groups',
    login_button_enabled INTEGER NOT NULL DEFAULT 0,  -- 首页统一认证入口开关
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 服务端会话
CREATE TABLE IF NOT EXISTS auth_sessions (
    id TEXT PRIMARY KEY,                  -- session token（随机 256bit，存哈希更佳）
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,
    csrf_token TEXT NOT NULL              -- 双提交 CSRF 令牌
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);

-- 登录失败限流记录
CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL,             -- 客户端标识（IP / 用户名）
    attempted_at TEXT NOT NULL DEFAULT (datetime('now')),
    success INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_login_attempts_source ON login_attempts(source_key, attempted_at);

-- OIDC 登录临时态（state/nonce/PKCE），短生命周期
CREATE TABLE IF NOT EXISTS oidc_login_state (
    state TEXT PRIMARY KEY,
    nonce TEXT NOT NULL,
    code_verifier TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

关于资源归属（多租户隔离）：现有 `instances`、`sessions` 与 `image_generations` 表无 `user_id`。为支持资源多租户隔离（需求 7.5），迁移将向这三张表补充可空列 `created_by TEXT`（引用 `users(id)`，旧数据为 NULL，视为无归属——对所有人可见或归属管理员）。运行/生成/创建接口在鉴权后写入当前用户 id。

### 迁移策略（`database.py::_migrate()`）

沿用现有幂等模式：`schema.sql` 负责新表创建（`IF NOT EXISTS`）；`_migrate()` 负责对已存在表补列与播种，全部幂等：

1. 向 `instances`、`sessions` 与 `image_generations` 三张表补充 `created_by TEXT`（`PRAGMA table_info` 检测后 `ALTER TABLE ... ADD COLUMN`，可空，旧数据保持 NULL）。
2. 播种 Seed_Admin：若 `user_roles` 中不存在任何 `super_admin`，则读取环境变量 `SEED_ADMIN_USERNAME`（默认 `admin`）与 `SEED_ADMIN_PASSWORD`；若后者缺失则生成随机初始密码并 `logger.warning` 输出一次，随后创建本地账号（`must_change_password=1`）并写入 `user_roles`。
3. 播种 `sso_config` 单例行（`INSERT OR IGNORE ... (id=1)`，`login_button_enabled=0`）。

配套 `tests/test_auth_migration.py`：验证补列幂等、Seed_Admin 幂等（多次 `init_db` 不重复创建、已存在时不覆盖）、旧数据保留。

## Components and Interfaces
### 角色→能力映射（`services/rbac.py`）

```python
CAPABILITIES = frozenset({
    "instance:read", "instance:write", "session:run", "chat:use", "image:use",
    "resource:read:all", "dashboard:read",
    "user:manage", "role:manage", "sso:manage",
})

ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "super_admin": CAPABILITIES,  # 全部，含 resource:read:all
    "admin": frozenset({
        "instance:read", "instance:write", "session:run", "chat:use",
        "image:use", "resource:read:all", "dashboard:read",
    }),
    "tester": frozenset({
        "instance:read", "instance:write", "session:run", "chat:use",
        "image:use", "dashboard:read",
    }),
    "viewer": frozenset({"instance:read", "dashboard:read"}),
}

def capabilities_for(roles: set[str]) -> frozenset[str]:
    """返回用户所有角色能力的并集（需求 6.7）。"""
    result: set[str] = set()
    for role in roles:
        result |= ROLE_CAPABILITIES.get(role, frozenset())
    return frozenset(result)
```

> **资源隔离设计原则：** 所有已认证用户默认可读写**自己的**资源——这是基线行为，无需额外能力控制。`resource:read:all` 赋予 admin/super_admin 查看并操作**所有用户**资源的权力。tester 拥有 `instance:write` 以创建和管理自己的实例，但不具备 `resource:read:all`，因此只能看到自己的数据。viewer 只具备 `instance:read`（仅自己的）和 `dashboard:read`（仅自己的统计）。

### 鉴权依赖（`app/api/deps.py`）

```python
async def get_current_user(
    request: Request, db: aiosqlite.Connection = Depends(get_db)
) -> CurrentUser:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="未认证")
    session = await auth_service.load_session(db, token)  # 校验存在且未过期
    if session is None:
        raise HTTPException(status_code=401, detail="会话无效或已过期")
    return await auth_service.load_current_user(db, session.user_id)

def require_permission(capability: str):
    async def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if capability not in user.capabilities:
            raise HTTPException(status_code=403, detail="权限不足")
        return user
    return _dep
```

现有路由改造示例（仅新增守卫，不改业务逻辑）：

```python
# app/api/instances.py
@router.post("", status_code=HTTP_201_CREATED)
async def create_instance(
    data: InstanceCreate,
    db: aiosqlite.Connection = Depends(get_db),
    user: CurrentUser = Depends(require_permission("instance:write")),
):
    ...
```

### 资源多租户隔离实现（需求 7.5）

所有资源的 CRUD 接口统一遵循以下隔离逻辑：

```python
# 示例：获取实例列表（list 接口）
async def list_instances(user: CurrentUser, db: Connection):
    if "resource:read:all" in user.capabilities:
        rows = await db.execute("SELECT * FROM instances ORDER BY created_at DESC")
    else:
        rows = await db.execute(
            "SELECT * FROM instances WHERE created_by = ? ORDER BY created_at DESC",
            (user.id,)
        )
    ...

# 示例：按 ID 获取单个资源（detail/update/delete 接口统一模式）
async def get_instance(instance_id: str, user: CurrentUser, db: Connection):
    row = await db.execute("SELECT * FROM instances WHERE id = ?", (instance_id,))
    if not row:
        raise HTTPException(404)
    if "resource:read:all" not in user.capabilities and row["created_by"] != user.id:
        raise HTTPException(404)  # 404 而非 403，不泄露资源存在性
    ...

# 示例：创建资源时记录归属
async def create_instance(data: InstanceCreate, user: CurrentUser, db: Connection):
    await db.execute(
        "INSERT INTO instances (id, ..., created_by) VALUES (?, ..., ?)",
        (new_id, ..., user.id),
    )
    ...
```

此模式同样适用于 `sessions`、`image_generations`、`chat sessions` 与 `dashboard` 统计接口：
- **instances**：list 按 `created_by` 过滤（admin/super_admin 不过滤）；get/update/delete 校验 owner。
- **sessions**（语音会话）：同上。
- **image_generations**：同上。
- **chat**：session 创建时写入 `created_by`，后续消息的归属继承自 session。
- **dashboard**：统计数据按 `created_by` 过滤（admin/super_admin 看全局）。
- **history**：统一按资源归属过滤，不再单独区分 `history:read:own` / `history:read:all`。

### API 端点清单

认证：
- `POST /api/auth/login` — 本地登录，成功下发 Session_Cookie（需求 2、12.4）。
- `POST /api/auth/logout` — 登出，失效会话并清 Cookie（需求 12.3）。
- `GET  /api/auth/me` — 返回当前用户、角色、能力集合（需求 12.4）。
- `POST /api/auth/change-password` — 改密，满足强度后清除强制改密标记（需求 3.3–3.5）。

SSO：
- `GET  /api/auth/sso/login` — 生成 state/nonce/PKCE 并 302 到 Authentik（需求 4.1、4.7）。
- `GET  /api/auth/sso/callback` — 回调：校验 state → 换 token → JWKS 验签 + nonce/iss/aud → userinfo → 自动开通 + 角色计算 → 建会话（需求 4.2–4.6、5）。

管理后台：
- `GET/POST/PUT/DELETE /api/admin/users` `/api/admin/users/{id}`（`user:manage`，需求 11）。
- `GET/POST/PUT/DELETE /api/admin/group-mappings`（`role:manage`，需求 10）。
- `GET/PUT /api/admin/sso-config`（`sso:manage`，client_secret 脱敏返回，需求 9）。

`GET /api/auth/sso/public-config` — 无需认证，仅返回登录页所需的公开信息（`login_button_enabled`），供登录页决定是否显示 SSO 按钮（需求 1.3/1.4）。不含任何机密字段。

### OIDC 服务（`services/oidc_service.py`）

- `discover()`：若配置了 discovery_url，拉取并缓存 authorization/token/userinfo/jwks 端点（需求 9.4）。
- `build_authorization_url(state, nonce, code_challenge)`：拼接 authorize URL，`scope` 取配置，`code_challenge_method=S256`。
- `exchange_code(code, code_verifier)`：向 token 端点换取 tokens（需求 4.2）。
- `verify_id_token(id_token, nonce)`：用 JWKS 验签，校验 iss/aud/exp 与 nonce（需求 4.4/4.5）。
- `fetch_userinfo(access_token)`：取用户信息与 groups claim（需求 4.6）。

### 加密服务（`services/crypto_service.py`）

- 应用密钥来自环境变量 `AUTH_SECRET_KEY`（需求 13.4）。使用对称加密（如 `cryptography` 的 Fernet，或 AES-GCM）加解密 `client_secret`。
- `encrypt(plaintext) -> str` / `decrypt(ciphertext) -> str`。
- 返回配置给前端时仅暴露 `client_secret_set: bool`，不返回密文或明文（需求 9.3、13.5）。

> 依赖新增：`passlib[bcrypt]`（或 `argon2-cffi`）、`cryptography`、`python-jose[cryptography]`（或 `PyJWT` + `cryptography`）用于 JWKS 验签。将加入 `pyproject.toml` 依赖并说明 `X | Y` 的 isinstance 写法（ruff UP038）。

## OIDC 登录时序

```
用户            前端(SPA)         后端(FastAPI)                Authentik
 |  点击统一认证入口 |                  |                            |
 |----------------->| GET /api/auth/sso/login                       |
 |                  |----------------->| 生成 state/nonce/PKCE       |
 |                  |                  | 存 oidc_login_state         |
 |                  |    302 到 authorize (含 state,challenge,nonce) |
 |                  |------------------------------------------------>|
 |  在 Authentik 认证 |                 |                            |
 |<------------------------------------------------------------------|
 |  302 回 callback?code&state         |                            |
 |----------------------------------->| GET /api/auth/sso/callback  |
 |                  |                  | 校验 state (需求4.2/4.3)     |
 |                  |                  | code+verifier 换 token ----->|
 |                  |                  |<---- tokens                 |
 |                  |                  | JWKS 验签+nonce (需求4.4/4.5)|
 |                  |                  | GET userinfo -------------->|
 |                  |                  |<---- userinfo + groups      |
 |                  |                  | 自动开通+角色计算(需求5)      |
 |                  |                  | 建 auth_session, 下发 Cookie |
 |                  |   302 回 SPA 首页（已登录）                     |
 |<-----------------|                  |                            |
```

## 前端页面与路由守卫

### 会话上下文与守卫

```tsx
// components/auth/AuthProvider.tsx —— 启动时请求 /api/auth/me
interface AuthState {
  user: { id: string; username: string } | null
  roles: string[]
  capabilities: string[]
  loading: boolean
}

// components/auth/ProtectedRoute.tsx
function ProtectedRoute({ capability, children }: {
  capability?: string; children: React.ReactNode
}) {
  const { user, capabilities, loading } = useAuth()
  if (loading) return <FullPageSpinner />
  if (!user) return <Navigate to="/login" replace />           // 需求 8.4
  if (capability && !capabilities.includes(capability))
    return <Navigate to="/" replace />                          // 需求 8.2
  return <>{children}</>
}
```

`App.tsx` 路由改造：新增 `/login`；其余路由包裹 `ProtectedRoute` 并标注所需能力；新增 `/admin/users`、`/admin/group-mappings`、`/admin/sso` 三个后台页面（分别要求 `user:manage`、`role:manage`、`sso:manage`）。`Sidebar` 依据 `capabilities` 隐藏无权入口（需求 8.3、8.5）。

`useApi`/所有 fetch 调用需加 `credentials: 'include'`（需求 13.2），并在收到 401 时跳转登录页（需求 8.4）。

### 登录页（`pages/LoginPage.tsx`）

- 上方：用户名/密码表单 + 登录按钮（需求 1.2、1.6）。
- 下方：调用 `GET /api/auth/sso/public-config`，当 `login_button_enabled` 为真时渲染"统一认证入口"按钮（需求 1.3/1.4），点击跳 `/api/auth/sso/login`。
- 背景采用不超过 95% 亮度的色值（如中性深色渐变或 `--color-muted`），避免白底不可见（需求 1.5）。使用现有 Radix/shadcn 输入与按钮组件。

## 权限对照表（需求 7、8）

### 后端 API → 所需能力

| 方法与路径 | 所需能力 |
| --- | --- |
| `GET /api/health` | 无（公开，需求 7.6） |
| `POST /api/auth/login`、`/api/auth/sso/login`、`/api/auth/sso/callback`、`GET /api/auth/sso/public-config` | 无（公开，需求 7.6） |
| `GET /api/auth/me`、`POST /api/auth/logout`、`POST /api/auth/change-password` | 仅需已认证 |
| `GET /api/instances`、`GET /api/instances/{id}` | `instance:read`（无 `resource:read:all` 时仅返回/允许自己的；有则返回全部，需求 7.5） |
| `POST/PUT/DELETE /api/instances*` | `instance:write`（无 `resource:read:all` 时仅可操作自己的；有则可操作全部） |
| `POST /api/sessions*`（创建/运行语音会话） | `session:run`（创建时写入 `created_by`） |
| `GET /api/sessions*`（查看会话） | 已认证（无 `resource:read:all` 时仅返回自己的，有则返回全部，需求 7.5） |
| `POST /api/chat*` | `chat:use`（session 创建时写入 `created_by`，消息归属继承自 session） |
| `GET /api/chat*`（查看对话历史） | 已认证（无 `resource:read:all` 时仅返回自己的 session，有则返回全部） |
| `POST /api/images*` | `image:use`（创建时写入 `created_by`） |
| `GET /api/images*`（查看图片历史） | 已认证（无 `resource:read:all` 时仅返回自己的，有则返回全部） |
| `GET /api/dashboard*` | `dashboard:read`（无 `resource:read:all` 时统计仅含自己的数据；有则全局统计） |
| `GET /api/history*` | 已认证（无 `resource:read:all` 时仅返回自己的记录，有则返回全部，需求 7.5） |
| `*/api/admin/users*` | `user:manage` |
| `*/api/admin/group-mappings*` | `role:manage` |
| `GET/PUT /api/admin/sso-config` | `sso:manage` |
| `/internal/*`（agent 内部回调） | 保持内部隔离（不经浏览器会话，按现有内部机制/网络隔离） |

### 前端路由 → 所需能力

| 路由 | 所需能力 |
| --- | --- |
| `/login` | 无 |
| `/`（仪表盘） | `dashboard:read` |
| `/instances`、`/instances/:id` | `instance:read`（写操作按钮需 `instance:write`） |
| `/instances/new` | `instance:write` |
| `/sessions/new` | `session:run` |
| `/chat/new` | `chat:use` |
| `/images/new` | `image:use` |
| `/history`、`/history/:id`、`/history/image/:id` | 已认证（列表按 `resource:read:all` 过滤归属） |
| `/admin/users` | `user:manage` |
| `/admin/group-mappings` | `role:manage` |
| `/admin/sso` | `sso:manage` |

## 安全设计

- **会话**：session token 为 256bit 随机值，服务端存其记录并设 `expires_at`（默认 8 小时，需求 12.1/12.2）。Cookie 属性 `HttpOnly; Secure; SameSite=Lax`（同源部署适配，需求 2.5、12）。登出与禁用用户时删除会话行使其立即失效（需求 11.4、12.3）。
- **CSRF**：SameSite=Lax 为主要防护；对状态变更接口采用双提交令牌（`auth_sessions.csrf_token` + 前端自定义请求头 `X-CSRF-Token`）校验（需求 13.3）。
- **CORS 收紧**：将 `allow_origins=["*"]` 改为从环境变量读取的可信来源列表（同源部署下默认无需跨域），并保留 `allow_credentials=True` 仅对显式来源生效（需求 13.1）。文档中明确当前 `*` + credentials 组合对携带 Cookie 无效且不安全。
- **密码**：bcrypt/argon2 哈希（需求 2.3），最小长度 12（需求 3.4/3.5）。
- **登录限流**：同一 `source_key` 60 秒内失败达 5 次则 60 秒内返回 429（需求 2.4）。
- **OIDC**：state（CSRF 防护）、nonce（重放防护）、PKCE S256（授权码拦截防护）；回调校验 state、验签 ID Token、校验 iss/aud/nonce（需求 4）。
- **敏感数据**：client_secret 及其它敏感配置对称加密存储、脱敏返回（需求 9.2/9.3、13.4）；日志不写密码/密钥/完整令牌明文（需求 13.5）。

## 与现有代码的集成点

1. `app/schema.sql`：追加 6 张新表 + 索引（`IF NOT EXISTS`）。
2. `app/database.py::_migrate()`：新增补列（`instances.created_by`、`sessions.created_by`、`image_generations.created_by`）与 Seed_Admin / sso_config 播种，保持幂等。
3. `app/main.py`：注册 `auth`、`sso`、`admin_users`、`admin_roles`、`admin_sso` 路由；收紧 CORS 中间件；`/api/health` 与登录/回调保持公开。
4. 现有 `app/api/{instances,sessions,dashboard,chat,images,history}.py`：为每个端点补 `Depends(require_permission(...))`；所有资源列表/详情/更新/删除接口加入 owner 过滤逻辑——无 `resource:read:all` 时仅操作 `created_by` 等于当前用户的记录，有则不过滤（需求 7.5）。
5. `pyproject.toml`：新增 `passlib[bcrypt]`（或 argon2）、`cryptography`、`python-jose`/`PyJWT`，`httpx` 已在 dev；OIDC 需在运行时依赖含 HTTP 客户端（`aiohttp` 已有）。
6. 前端 `App.tsx`、`Sidebar`、`useApi`：接入 `AuthProvider`/`ProtectedRoute`、能力驱动导航、`credentials: 'include'` 与 401 跳转；新增 `LoginPage` 与三个后台页面。
7. 验证命令沿用：前端 `node_modules/.bin/tsc -b && node_modules/.bin/vite build --outDir ../backend/static && node_modules/.bin/vitest run`（不使用 pnpm）；后端 `.venv/bin/python -m pytest -q`。

## 验收标准可测试性预分析（Acceptance Criteria Testing Prework）

> 逐条判断验收标准是否适合自动化测试及测试类型（PROPERTY / EXAMPLE / EDGE_CASE / INTEGRATION / SMOKE）。

需求 1（登录页展示）
- 1.1 未认证重定向登录页：前端守卫行为，随输入路由变化 → PROPERTY（对任意受保护路由，未认证均重定向）。
- 1.2 表单元素存在：渲染断言 → EXAMPLE。
- 1.3/1.4 入口开关显隐：随开关布尔值变化 → PROPERTY（开关值决定按钮存在与否）。
- 1.5 背景亮度 → 视觉约束，不可计算断言 → 不测试。
- 1.6 加载中禁用按钮：具体交互 → EXAMPLE。

需求 2（本地登录）
- 2.1 正确凭据登录成功：随用户名/密码变化，属核心逻辑 → PROPERTY。
- 2.2 错误凭据统一拒绝且不泄露存在性：随输入变化 → PROPERTY（无论用户名是否存在，错误响应一致）。
- 2.3 密码哈希存储：round-trip（哈希后可验证、且不等于明文）→ PROPERTY。
- 2.4 限流：达到阈值后拒绝 → PROPERTY（对任意失败序列，第 6 次触发 429）。
- 2.5 会话 Cookie 属性：设置 httpOnly/Secure/SameSite → EXAMPLE。
- 2.6 禁用账号拒绝 → EXAMPLE/EDGE_CASE。

需求 3（引导管理员）
- 3.1 无 super_admin 时播种：幂等与存在性 → PROPERTY（与 3 一起）。
- 3.2 缺省密码生成并输出一次 → EXAMPLE。
- 3.3 强制改密拦截 → EXAMPLE。
- 3.4/3.5 密码强度阈值：随长度变化 → PROPERTY（长度≥12 接受、<12 拒绝）。

需求 4（SSO 登录）
- 4.1 生成 state/nonce/PKCE 并重定向 → PROPERTY（每次登录生成的 state/nonce/verifier 唯一且 challenge=S256(verifier)）。
- 4.2/4.3 state 一致性校验：随 state 匹配/不匹配变化 → PROPERTY。
- 4.4/4.5 ID Token 验签与 nonce/iss/aud 校验 → PROPERTY（篡改任一项则拒绝）。
- 4.6 userinfo 获取 groups → INTEGRATION（依赖外部 IdP，用 mock/示例）。
- 4.7 开关关闭时拒绝 SSO → EXAMPLE/EDGE_CASE。

需求 5（自动开通与角色）
- 5.1 首登自动建账号 → PROPERTY（对任意新 subject，登录后本地存在唯一账号）。
- 5.2 依映射赋角色 → PROPERTY。
- 5.3 无匹配默认 viewer → PROPERTY（对任意不含已映射组的 groups，结果含 viewer）。
- 5.4 再次登录按当前组更新角色 → PROPERTY（幂等/收敛：角色恒等于当前 groups 映射结果）。
- 5.5 建会话下发 Cookie → EXAMPLE。

需求 6（RBAC）
- 6.1 四角色存在 → EXAMPLE。
- 6.2–6.6 各角色能力集合 → EXAMPLE（固定映射，逐一断言）。
- 6.7 能力为并集 → PROPERTY（对任意角色子集，能力集合等于各角色能力并集）。

需求 7（后端保护）
- 7.1 未认证 401 → PROPERTY（对任意受保护接口，无会话 → 401）。
- 7.2 缺能力 403 且不执行业务 → PROPERTY（对任意接口与缺失能力用户 → 403）。
- 7.3 具备能力放行 → PROPERTY。
- 7.4/7.5 资源多租户隔离过滤 → PROPERTY（无 `resource:read:all` 时仅得自身记录，有则全部）。
- 7.6 公开接口无需认证 → EXAMPLE。

需求 7.5（资源多租户隔离）
- 7.5.1 创建资源记录归属 → EXAMPLE（创建后 `created_by` 等于当前用户）。
- 7.5.2 无 `resource:read:all` 用户仅看自己的实例 → PROPERTY。
- 7.5.3 有 `resource:read:all` 返回全部实例 → PROPERTY。
- 7.5.4 同理适用于其他资源类型 → PROPERTY（参数化资源类型）。
- 7.5.5 按 ID 访问他人资源返回 404 → PROPERTY（不泄露存在性）。
- 7.5.6 admin/super_admin 看所有 → 与 7.5.3 合并。

需求 8（前端守卫）
- 8.1/8.2 有/无能力渲染或拦截 → PROPERTY（能力决定渲染）。
- 8.3/8.5 导航显隐 → PROPERTY（入口存在性 = 是否具备对应能力）。
- 8.4 401 跳登录 → EXAMPLE。

需求 9（SSO 配置后台）
- 9.1 CRUD（sso:manage）→ EXAMPLE + 见 7.2 的权限属性。
- 9.2 client_secret 加密存储 → PROPERTY（round-trip：解密=原文，且落库值≠原文）。
- 9.3 返回脱敏 → PROPERTY（任意配置读取响应均不含明文/密文 secret）。
- 9.4 discovery 自动获取端点 → INTEGRATION（外部/mock）。
- 9.5 字段完整 → EXAMPLE。
- 9.6 开关持久化并影响登录页 → PROPERTY（写入后读取一致，见 round-trip）。
- 9.7 无 sso:manage → 403 → 见 7.2 属性。

需求 10（组映射）
- 10.1 CRUD（role:manage）→ EXAMPLE。
- 10.2 记录组名与角色 → EXAMPLE。
- 10.3 非法角色拒绝 → PROPERTY（对任意不属于四角色的取值，保存被拒）。
- 10.4 无 role:manage → 403 → 见 7.2 属性。

需求 11（用户管理）
- 11.1 列表/建/启停/改角色（user:manage）→ EXAMPLE。
- 11.2 建账号哈希+强制改密 → EXAMPLE（哈希属性并入 2.3）。
- 11.3 无 user:manage → 403 → 见 7.2 属性。
- 11.4 禁用使会话失效 → PROPERTY（禁用后该用户任意现存会话请求 → 401）。

需求 12（会话与登出）
- 12.1/12.2 生命周期与过期 401 → PROPERTY（对任意过期会话 → 401）。
- 12.3 登出失效并清 Cookie → EXAMPLE。
- 12.4 登录响应含身份/角色/能力 → EXAMPLE。

需求 13（安全加固）
- 13.1 CORS 收紧 → EXAMPLE/SMOKE（配置断言）。
- 13.2 前端携带凭据 → EXAMPLE。
- 13.3 CSRF 双提交校验 → PROPERTY（缺失/错误 CSRF 令牌的状态变更请求被拒）。
- 13.4 敏感字段加密（密钥来自环境）→ 与 9.2 合并。
- 13.5 日志脱敏 → EXAMPLE（断言日志不含明文）。

### 属性去冗余反思（Property Reflection）

- 2.3 与 13.4/9.2 的"哈希/加密可验证且不等于明文"可归并为两条独立 round-trip 属性：一条针对密码哈希（单向可验证），一条针对可逆加密（解密=原文且密文≠原文）。
- 7.1/7.2/7.3 合并为一条"接口守卫"属性（能力决定 401/403/放行三态）；9.7、10.4、11.3 均是 7.2 在具体能力上的实例，不再单列。
- 9.3 与 9.2 相关但验证点不同（脱敏输出 vs 加密存储），各自保留。
- 6.2–6.6 为固定映射用示例断言覆盖；6.7 保留为并集属性。
- 5.2/5.3/5.4 可合并为一条"角色恒等于当前 groups 经映射的结果，无匹配则为 {viewer}"的收敛属性。
- 原 Property 12 的 `history:read:own/all` 过滤已推广为 Property 21 的通用资源多租户隔离属性（覆盖 instances/sessions/image_generations/chat/dashboard），两者互补：Property 12 侧重列表过滤逻辑，Property 21 额外覆盖单资源 404 与创建归属写入。

## Correctness Properties
*属性是指在系统所有合法执行下都应成立的特征或行为，是人类可读规格与机器可验证正确性保证之间的桥梁。*

### Property 1: 能力集合为角色能力并集

*对于任意*角色子集 R（取自四个合法角色），`capabilities_for(R)` 返回的能力集合等于 R 中每个角色对应能力集合的并集，且不包含任何角色都未授予的能力。

**Validates: Requirements 6.7, 6.3, 6.4, 6.5, 6.6**

### Property 2: 接口守卫按能力三态判定

*对于任意*受保护接口与任意用户会话状态：无有效会话时返回 401；已认证但能力集合不含该接口所需能力时返回 403 且不执行业务逻辑；能力集合包含所需能力时放行。

**Validates: Requirements 7.1, 7.2, 7.3, 9.7, 10.4, 11.3**

### Property 3: 密码哈希单向可验证

*对于任意*非空密码字符串，存储的哈希值不等于明文，且用同一明文校验返回真、用任意不同明文校验返回假。

**Validates: Requirements 2.3**

### Property 4: 错误登录不泄露账号存在性

*对于任意*用户名与错误密码组合（无论该用户名是否存在），本地登录失败响应的状态码与提示文案一致，不区分"用户不存在"与"密码错误"。

**Validates: Requirements 2.2**

### Property 5: 登录失败限流阈值

*对于任意*来源，在 60 秒窗口内累计 5 次失败后，随后 60 秒内的登录尝试均返回 429。

**Validates: Requirements 2.4**

### Property 6: 密码强度阈值

*对于任意*新密码字符串，长度不小于 12 时改密被接受并清除强制改密标记，长度小于 12 时改密被拒绝。

**Validates: Requirements 3.4, 3.5**

### Property 7: OIDC 登录态生成唯一且 PKCE 一致

*对于任意*一次 SSO 登录发起，生成的 state、nonce、code_verifier 均为高熵唯一值，且 code_challenge 等于 code_verifier 的 S256 变换。

**Validates: Requirements 4.1**

### Property 8: OIDC 回调 state 校验

*对于任意*回调请求，当携带 state 与登录态保存的 state 相等时继续换取令牌，否则拒绝登录。

**Validates: Requirements 4.2, 4.3**

### Property 9: ID Token 校验拒绝篡改

*对于任意*被篡改的 ID Token（签名、issuer、audience 或 nonce 任一不匹配），令牌校验返回失败并拒绝登录。

**Validates: Requirements 4.4, 4.5**

### Property 10: SSO 用户自动开通唯一性

*对于任意*新的 OIDC subject，首次登录后本地恰好存在一个对应的 SSO_User，重复登录不产生重复账号。

**Validates: Requirements 5.1**

### Property 11: 角色由当前分组映射收敛决定

*对于任意* groups claim 集合，计算所得角色集合等于各已配置 Group_Role_Mapping 命中角色之并集；若无任何命中，则角色集合为 `{viewer}`；再次以相同 groups 计算结果不变（幂等）。

**Validates: Requirements 5.2, 5.3, 5.4**

### Property 12: 资源按 resource:read:all 隔离过滤

*对于任意*资源数据集合（instances、sessions、image_generations）与用户，不具备 `resource:read:all` 的用户查询结果只包含 `created_by` 等于该用户的记录；具备 `resource:read:all` 的用户查询结果包含全部记录。

**Validates: Requirements 7.4, 7.5**

### Property 13: 可逆加密 round-trip 且落库非明文

*对于任意* client_secret 明文，加密后解密等于原文，且存储的密文不等于明文。

**Validates: Requirements 9.2, 13.4**

### Property 14: SSO 配置返回脱敏

*对于任意* SSO_Config 读取响应，响应体不包含 client_secret 的明文或密文，仅包含"是否已设置"的布尔标识。

**Validates: Requirements 9.3, 13.5**

### Property 15: 组映射角色取值校验

*对于任意*角色取值，当其不属于 `{super_admin, admin, tester, viewer}` 时，创建 Group_Role_Mapping 被拒绝。

**Validates: Requirements 10.3**

### Property 16: 禁用用户会话立即失效

*对于任意*被禁用的用户，其所有现存会话对受保护接口的后续请求均返回 401，且该用户无法再次登录。

**Validates: Requirements 11.4, 2.6**

### Property 17: 会话过期后拒绝

*对于任意*超过 `expires_at` 的会话，使用该会话访问受保护接口返回 401。

**Validates: Requirements 12.1, 12.2**

### Property 18: CSRF 令牌校验状态变更请求

*对于任意*状态变更请求（POST/PUT/DELETE），当缺失或提供错误的 CSRF 令牌时被拒绝，提供与会话匹配的 CSRF 令牌时放行。

**Validates: Requirements 13.3**

### Property 19: 登录页 SSO 入口显隐等于开关

*对于任意* `login_button_enabled` 布尔取值，登录页公开配置返回该取值，且登录页当且仅当取值为真时渲染统一认证入口按钮。

**Validates: Requirements 1.3, 1.4, 9.6**

### Property 20: 未认证访问受保护前端路由重定向

*对于任意*受保护前端路由，未认证状态下访问均被重定向到登录页。

**Validates: Requirements 1.1, 8.4**

### Property 21: 资源多租户隔离

*对于任意*不具备 `resource:read:all` 的用户，所有资源列表接口（instances、sessions、image_generations、chat sessions、dashboard）仅返回 `created_by` 等于该用户的记录；按 ID 直接访问不归属于自己的资源返回 HTTP 404（不泄露存在性）。具备 `resource:read:all` 的用户（admin/super_admin）可查看和操作全部用户的资源。

**Validates: Requirements 7.5.1, 7.5.2, 7.5.3, 7.5.4, 7.5.5, 7.5.6**

## Error Handling
鉴权系统对各类错误采用统一、可预期且不泄露敏感信息的处理策略：

- **401 未认证**：请求未携带有效 Session_Cookie、会话不存在、会话已过期或被禁用用户的现存会话，访问除登录/SSO 回调/`/api/health` 外的受保护接口时，统一返回 HTTP 401（需求 7.1、11.4、12.2）。前端收到 401 一律清理本地会话状态并重定向登录页（需求 8.4）。
- **403 能力不足**：已认证但能力集合不含接口所需能力时返回 HTTP 403，且不执行任何业务逻辑（需求 7.2）；`user:manage`、`role:manage`、`sso:manage` 相关后台接口对缺失对应能力者一律 403（需求 9.7、10.4、11.3）。
- **429 登录限流**：同一 `source_key` 在 60 秒窗口内失败达 5 次后，后续 60 秒内的登录尝试统一返回 HTTP 429，不区分账号是否存在（需求 2.4）。
- **OIDC 校验失败**：回调 state 缺失或不匹配、ID Token 签名验证失败、nonce/issuer/audience 任一不匹配时，终止登录流程、清理对应 `oidc_login_state` 临时态，返回统一的"认证失败"错误并重定向登录页，不向前端暴露具体失败细节（需求 4.3、4.5）。
- **输入校验错误（400）**：如改密时新密码长度小于 12（需求 3.5）、组→角色映射的角色取值不属于四个合法角色（需求 10.3）等非法输入，返回 HTTP 400 并给出可读的校验错误信息，不落库无效数据。
- **本地登录失败**：用户名不存在或密码错误时返回统一的"用户名或密码错误"提示，不区分两种情形以避免账号枚举（需求 2.2）。
- **加解密与外部 IdP 不可用降级**：`AUTH_SECRET_KEY` 缺失或 client_secret 解密失败时，SSO 相关流程返回配置错误并保持本地登录路径可用（应急登录不受影响）；Authentik 的 discovery/token/userinfo/jwks 端点不可达或超时时，向用户返回统一的"统一认证暂不可用"提示，本地账号登录仍可正常工作（需求 9.4、4.6）。
- **日志脱敏**：所有错误与审计日志均不写入密码明文、client_secret 明文或完整令牌，仅记录必要的错误类型与脱敏标识（需求 13.5）。

## Testing Strategy
- **属性测试**：使用现有 `hypothesis`（后端，`max_examples>=100`，见 `tests/test_migration.py` 约定）覆盖上述属性 1–21 中的后端项；前端使用 `vitest` + Testing Library 覆盖属性 19、20 与守卫渲染（可用轻量 fast-check 或参数化输入模拟"对任意"）。每个属性测试标注 `Feature: user-auth-rbac-sso, Property N: ...`。
- **单元/示例测试**：覆盖固定映射（6.1–6.6）、Cookie 属性、登出、登录响应负载、discovery/userinfo（用 mock/示例，属 INTEGRATION）。
- **迁移测试**：`tests/test_auth_migration.py` 验证补列与 Seed_Admin/sso_config 播种幂等、旧数据保留（沿用 `test_migration.py` 模式）。
- 外部 Authentik 交互（4.6、9.4）以 mock HTTP 或本地 stub 进行，不做真实网络往返。
