# Requirements Document
## Introduction
本功能为现有的 Azure OpenAI 测试平台（FastAPI 后端 + React/TypeScript 前端，同源部署）新增一套完整的用户鉴权与授权系统。当前平台完全没有鉴权，所有接口与页面对任何访问者开放。本功能引入：

1. 一个美观大气的登录页：上方为本地用户名/密码登录表单，下方为可开关显隐的"统一认证入口"（Authentik SSO）按钮。
2. 两条并存的登录路径：本地账号（存于应用自身的 SQLite 库、密码哈希、用作超级管理员与应急登录）与 Authentik SSO（OIDC 授权码 + PKCE 流程，首次登录自动开通本地账号）。
3. 基于角色的访问控制（RBAC）：四级角色（super_admin、admin、tester、viewer），细粒度能力（capability）权限，后端接口与前端路由按能力保护。
4. 组→角色映射：超级管理员可在后台维护 Authentik 组名到平台角色的映射，匹配不到时默认赋予 viewer。
5. 超级管理员后台：管理全部 Authentik SSO 配置（含加密存储的 client_secret）并开关首页 SSO 入口。
6. 安全加固：会话 Cookie（httpOnly + Secure + SameSite）、OIDC state/nonce/PKCE 防护、敏感配置加密存储与脱敏返回、登录限流、CSRF 防护，并收紧当前不安全的 CORS 配置。

本功能只新增鉴权相关代码，不改变现有测试功能（实例管理、语音会话、对话、图片、历史、仪表盘）的业务逻辑，仅为其加上访问保护。

## Glossary
- **Auth_System（鉴权系统）**：本功能新增的后端鉴权与授权子系统，负责登录、会话、权限校验。
- **Local_Account（本地账号）**：存储于应用 SQLite 库、使用密码哈希的账号，用于超级管理员与应急（break-glass）登录。
- **SSO_User（SSO 用户）**：通过 Authentik OIDC 登录、由系统在本地自动开通（provision）的账号。
- **Authentik**：外部身份提供方（IdP），提供 OIDC 授权码流程与 `groups` claim。
- **OIDC_Flow（OIDC 流程）**：Authentik 授权码 + PKCE 流程，包含 state、nonce、PKCE 防护，回调后以 code 换取 token 并调用 userinfo。
- **Role（角色）**：四级之一，取值为 `super_admin`、`admin`、`tester`、`viewer`。
- **Capability（能力）**：细粒度权限标识，例如 `instance:read`、`session:run`、`sso:manage`。
- **Group_Role_Mapping（组→角色映射）**：数据库中维护的 Authentik 组名到平台角色的映射记录。
- **SSO_Config（SSO 配置）**：Authentik 连接与协议参数（issuer、client_id、加密的 client_secret、端点、scopes、groups claim 字段名、首页入口开关等）。
- **Session_Cookie（会话 Cookie）**：httpOnly + Secure + SameSite 的会话凭据 Cookie。
- **Super_Admin（超级管理员）**：拥有 `super_admin` 角色的用户，可管理用户、角色映射与 SSO 配置。
- **Route_Guard（路由守卫）**：后端依赖注入式权限校验（`require_permission`）与前端受保护路由组件。
- **Seed_Admin（引导管理员）**：系统首次启动时创建的首个 super_admin 本地账号。

## Requirements
### 需求 1：登录页展示

**用户故事：** 作为访问平台的用户，我希望看到一个美观大气的登录页，上方是本地账号登录表单、下方是可选的统一认证入口，以便我用合适的方式登录。

#### 验收标准

1. WHEN 未认证用户访问任意受保护的前端路由，THE Auth_System SHALL 将该用户重定向到登录页。
2. THE 登录页 SHALL 在表单区域上方展示本地用户名输入框、密码输入框与登录按钮。
3. WHERE SSO_Config 中"显示统一认证入口"开关处于开启状态，THE 登录页 SHALL 在本地登录表单下方展示"统一认证入口"按钮。
4. WHERE SSO_Config 中"显示统一认证入口"开关处于关闭状态，THE 登录页 SHALL 隐藏"统一认证入口"按钮并仅展示本地登录表单。
5. THE 登录页 SHALL 使用不高于 95% 亮度的背景色，以确保在白底主题下所有文本与控件可见。
6. WHILE 登录请求处于处理中，THE 登录页 SHALL 禁用登录按钮并展示加载状态指示。

### 需求 2：本地账号登录

**用户故事：** 作为超级管理员或应急登录用户，我希望使用本地用户名与密码登录，以便在 SSO 不可用时仍能访问与管理平台。

#### 验收标准

1. WHEN 用户提交与某个启用状态 Local_Account 匹配的用户名与正确密码，THE Auth_System SHALL 创建认证会话并返回该用户的角色与能力集合。
2. IF 用户提交的用户名不存在或密码不匹配，THEN THE Auth_System SHALL 拒绝登录并返回统一的"用户名或密码错误"提示，不透露用户名是否存在。
3. THE Auth_System SHALL 使用 bcrypt 或 argon2 对本地账号密码进行哈希后存储，不以明文保存密码。
4. IF 同一来源在 60 秒内失败登录次数达到 5 次，THEN THE Auth_System SHALL 在随后的 60 秒内拒绝该来源的新登录尝试并返回限流响应（HTTP 429）。
5. WHEN 认证会话创建成功，THE Auth_System SHALL 通过 httpOnly + Secure + SameSite 的 Session_Cookie 下发会话凭据。
6. WHERE Local_Account 被标记为禁用，THE Auth_System SHALL 拒绝该账号的登录并返回账号不可用提示。

### 需求 3：引导管理员与首次改密

**用户故事：** 作为平台部署者，我希望系统首次启动时自动具备一个超级管理员账号，以便我能立即登录并完成初始配置。

#### 验收标准

1. WHEN Auth_System 初始化且数据库中不存在任何 `super_admin` 角色的 Local_Account，THE Auth_System SHALL 依据启动配置（环境变量提供的用户名与初始密码）创建一个 Seed_Admin 账号。
2. WHERE 启动配置未提供 Seed_Admin 的初始密码，THE Auth_System SHALL 生成一次性随机初始密码并在启动日志中输出该密码一次。
3. WHEN Seed_Admin 首次登录成功且其账号被标记为"需强制改密"，THE Auth_System SHALL 要求该用户在访问其他受保护资源前完成密码修改。
4. WHEN 用户提交的新密码长度不小于 12 个字符，THE Auth_System SHALL 更新该账号的密码哈希并清除"需强制改密"标记。
5. IF 用户提交的新密码长度小于 12 个字符，THEN THE Auth_System SHALL 拒绝改密并返回密码强度不足的提示。

### 需求 4：Authentik SSO 登录

**用户故事：** 作为企业用户，我希望点击统一认证入口通过 Authentik 登录，以便复用企业身份而无需单独记忆平台密码。

#### 验收标准

1. WHEN 用户点击"统一认证入口"，THE Auth_System SHALL 生成 state、nonce 与 PKCE code_verifier/code_challenge，并将用户重定向至 Authentik 授权端点。
2. WHEN Authentik 回调返回授权码且回调携带的 state 与本次登录会话保存的 state 一致，THE Auth_System SHALL 使用授权码与 code_verifier 向 token 端点换取令牌。
3. IF 回调携带的 state 与保存的 state 不一致或缺失，THEN THE Auth_System SHALL 拒绝本次登录并返回 OIDC 校验失败提示。
4. WHEN Auth_System 获取到 ID Token，THE Auth_System SHALL 使用 Authentik 的 JWKS 验证令牌签名并校验 nonce、issuer 与 audience。
5. IF ID Token 签名验证失败或 nonce/issuer/audience 校验不通过，THEN THE Auth_System SHALL 拒绝本次登录并返回令牌校验失败提示。
6. WHEN 令牌校验通过，THE Auth_System SHALL 调用 userinfo 端点获取用户信息与 groups claim。
7. WHERE SSO_Config 的"显示统一认证入口"开关处于关闭状态，THE Auth_System SHALL 拒绝发起或完成 SSO 登录流程并返回入口未启用提示。

### 需求 5：SSO 用户自动开通与角色赋予

**用户故事：** 作为通过 SSO 首次登录的用户，我希望系统自动为我创建平台账号并按我的分组赋予角色，以便我登录后立即拥有相应权限。

#### 验收标准

1. WHEN SSO 登录校验通过且本地不存在对应的 SSO_User，THE Auth_System SHALL 依据 userinfo 中的稳定用户标识自动创建本地 SSO_User 账号。
2. WHEN 创建或更新 SSO_User，THE Auth_System SHALL 依据 userinfo 的 groups claim 与 Group_Role_Mapping 计算并赋予该用户角色。
3. IF SSO_User 的任一分组均未匹配到 Group_Role_Mapping，THEN THE Auth_System SHALL 为该用户赋予 `viewer` 角色。
4. WHEN 已存在的 SSO_User 再次登录且其分组发生变化，THE Auth_System SHALL 依据当前 groups claim 与 Group_Role_Mapping 重新计算并更新该用户角色。
5. WHEN SSO_User 账号创建或更新完成，THE Auth_System SHALL 创建认证会话并通过 Session_Cookie 下发会话凭据。

### 需求 6：RBAC 角色与能力

**用户故事：** 作为平台管理者，我希望不同角色拥有不同能力，以便按职责限制每个用户可执行的操作。

#### 验收标准

1. THE Auth_System SHALL 支持四个角色：`super_admin`、`admin`、`tester`、`viewer`。
2. THE Auth_System SHALL 将每个角色映射到一个能力集合，能力取值属于：`instance:read`、`instance:write`、`session:run`、`chat:use`、`image:use`、`resource:read:all`、`dashboard:read`、`user:manage`、`role:manage`、`sso:manage`。所有已认证用户默认可读写**自己的**资源（基线行为，无需能力控制）；`resource:read:all` 赋予查看**所有用户**资源的权力。
3. THE Auth_System SHALL 为 `super_admin` 赋予全部能力，包含 `user:manage`、`role:manage`、`sso:manage`、`resource:read:all`。
4. THE Auth_System SHALL 为 `admin` 赋予 `instance:read`、`instance:write`、`session:run`、`chat:use`、`image:use`、`resource:read:all`、`dashboard:read`，且不包含 `user:manage`、`role:manage`、`sso:manage`。
5. THE Auth_System SHALL 为 `tester` 赋予 `instance:read`、`instance:write`、`session:run`、`chat:use`、`image:use`、`dashboard:read`，且不包含 `resource:read:all`（仅可操作自己的资源）。
6. THE Auth_System SHALL 为 `viewer` 赋予 `instance:read`、`dashboard:read`，且不包含任何写入或运行类能力，也不包含 `resource:read:all`（仅可查看自己的资源）。
7. WHEN Auth_System 计算某用户的能力集合，THE Auth_System SHALL 返回该用户所有角色对应能力的并集。

### 需求 7：后端接口权限保护

**用户故事：** 作为平台安全负责人，我希望每个后端接口都按所需能力受控，以便未授权请求被一致拒绝。

#### 验收标准

1. IF 请求未携带有效 Session_Cookie 访问除登录、SSO 回调、健康检查以外的 `/api/` 接口，THEN THE Auth_System SHALL 返回 HTTP 401。
2. IF 已认证用户访问某接口但缺少该接口所需能力，THEN THE Auth_System SHALL 返回 HTTP 403 且不执行该接口的业务逻辑。
3. WHEN 已认证用户携带所需能力访问受保护接口，THE Auth_System SHALL 放行请求并执行原有业务逻辑。
4. WHERE 用户不具备 `resource:read:all`，THE Auth_System SHALL 对所有资源列表与详情接口仅返回归属于该用户的记录（参见需求 7.5 资源多租户隔离）。
5. WHERE 用户具备 `resource:read:all`（admin / super_admin），THE Auth_System SHALL 返回全部用户的资源记录（参见需求 7.5 资源多租户隔离）。
6. THE Auth_System SHALL 保持 `/api/health` 与登录、SSO 回调接口无需认证即可访问。

### 需求 7.5：资源多租户隔离

**用户故事：** 作为平台用户，我希望只看到和管理自己创建的资源（实例、对话、图片、语音会话），以便各用户之间的数据互不干扰；作为管理员，我希望能查看全部用户的资源以便监管。

#### 验收标准

1. WHEN 用户创建实例/对话/图片任务/语音会话，THE Auth_System SHALL 记录该资源的归属用户（`created_by` 字段）。
2. WHERE 用户仅具备 `instance:read` 而不具备 `resource:read:all`，THE Auth_System SHALL 仅返回归属于该用户的实例列表。
3. WHERE 用户具备 `resource:read:all`，THE Auth_System SHALL 返回全部用户的实例。
4. 同理适用于对话会话（chat sessions）、图片生成（image_generations）、语音会话（voice sessions）与仪表盘统计。
5. IF 用户尝试访问不归属于自己的资源（通过 ID 直接访问），THEN THE Auth_System SHALL 返回 HTTP 404（不泄露资源存在性）。
6. WHERE admin 或 super_admin 用户访问任何资源，THE Auth_System SHALL 返回全部用户的数据。

### 需求 8：前端路由守卫与入口显隐

**用户故事：** 作为登录用户，我希望前端只展示我有权访问的入口与页面，以便界面与我的权限一致。

#### 验收标准

1. WHEN 已认证用户访问其能力集合允许的前端路由，THE Route_Guard SHALL 渲染该页面。
2. IF 已认证用户访问其能力集合不允许的前端路由，THEN THE Route_Guard SHALL 阻止渲染并展示无权限提示或重定向到有权访问的默认页。
3. WHERE 用户缺少某功能对应的能力，THE 前端导航 SHALL 隐藏该功能的入口链接。
4. WHEN 用户会话过期或后端返回 HTTP 401，THE 前端 SHALL 将用户重定向到登录页。
5. WHERE 用户具备 `sso:manage`、`user:manage` 或 `role:manage`，THE 前端导航 SHALL 展示对应的后台管理入口。

### 需求 9：超级管理员 SSO 配置后台

**用户故事：** 作为超级管理员，我希望在后台管理全部 Authentik SSO 配置并开关首页入口，以便无需改代码即可调整认证接入。

#### 验收标准

1. WHERE 用户具备 `sso:manage`，THE Auth_System SHALL 允许该用户创建、查看、修改与删除 SSO_Config。
2. WHEN 超级管理员保存 SSO_Config 的 client_secret，THE Auth_System SHALL 使用应用密钥对 client_secret 进行对称加密后存储，不以明文落库。
3. WHEN 任意接口返回 SSO_Config，THE Auth_System SHALL 对 client_secret 进行脱敏（不返回明文，仅标识是否已设置）。
4. WHEN 超级管理员提供 issuer 或 discovery URL，THE Auth_System SHALL 支持从 discovery 文档自动获取 authorization、token、userinfo 与 jwks 端点。
5. THE SSO_Config SHALL 包含可编辑字段：issuer/discovery URL、client_id、client_secret、redirect URI、scopes、groups claim 字段名，以及"是否在登录页显示统一认证入口"开关。
6. WHEN 超级管理员切换"显示统一认证入口"开关，THE Auth_System SHALL 持久化该开关状态并使登录页据此显隐入口。
7. IF 不具备 `sso:manage` 的用户请求任何 SSO_Config 管理接口，THEN THE Auth_System SHALL 返回 HTTP 403。

### 需求 10：组→角色映射管理

**用户故事：** 作为超级管理员，我希望在后台维护 Authentik 组名到平台角色的映射，以便控制 SSO 用户登录后获得的权限。

#### 验收标准

1. WHERE 用户具备 `role:manage`，THE Auth_System SHALL 允许该用户创建、查看、修改与删除 Group_Role_Mapping。
2. THE Group_Role_Mapping SHALL 记录 Authentik 组名与其对应的平台角色。
3. WHEN 超级管理员创建的 Group_Role_Mapping 指向的角色不属于四个合法角色之一，THE Auth_System SHALL 拒绝保存并返回校验错误。
4. IF 不具备 `role:manage` 的用户请求任何 Group_Role_Mapping 管理接口，THEN THE Auth_System SHALL 返回 HTTP 403。

### 需求 11：用户管理后台

**用户故事：** 作为超级管理员，我希望管理平台用户及其角色，以便维护账号与权限。

#### 验收标准

1. WHERE 用户具备 `user:manage`，THE Auth_System SHALL 允许该用户查看用户列表、创建本地账号、启用或禁用账号、以及调整账号角色。
2. WHEN 超级管理员创建本地账号并提供密码，THE Auth_System SHALL 以哈希形式存储该密码并将账号标记为"需强制改密"。
3. IF 不具备 `user:manage` 的用户请求任何用户管理接口，THEN THE Auth_System SHALL 返回 HTTP 403。
4. WHEN 超级管理员禁用某账号，THE Auth_System SHALL 使该账号后续登录被拒绝并使其现有会话失效。

### 需求 12：会话管理与登出

**用户故事：** 作为登录用户，我希望我的会话安全且可主动登出，以便控制账号访问。

#### 验收标准

1. THE Auth_System SHALL 为每个认证会话设置有限的生命周期（默认 8 小时）。
2. IF 会话超过其生命周期，THEN THE Auth_System SHALL 视该会话为过期并对其后续请求返回 HTTP 401。
3. WHEN 用户请求登出，THE Auth_System SHALL 使该会话失效并清除 Session_Cookie。
4. WHEN Auth_System 返回登录成功响应，THE Auth_System SHALL 提供该会话对应的用户身份、角色与能力集合供前端使用。

### 需求 13：安全加固与 CORS 收紧

**用户故事：** 作为平台安全负责人，我希望鉴权引入的同时收紧不安全的默认配置，以便凭据与会话受到保护。

#### 验收标准

1. THE Auth_System SHALL 将后端 CORS 配置从 `allow_origins=["*"]` 且 `allow_credentials=True` 收紧为同源或显式配置的可信来源列表。
2. WHEN 前端向后端发起需要认证的请求，THE 前端 SHALL 携带凭据（Cookie）发送请求。
3. WHERE 请求为会更改状态的非同源写操作，THE Auth_System SHALL 校验 CSRF 防护标记（如 SameSite Cookie 配合双提交令牌或自定义请求头）。
4. THE Auth_System SHALL 使用应用密钥对 SSO_Config 中的敏感字段进行加密，且应用密钥从环境变量读取，不硬编码于源码。
5. WHEN Auth_System 记录鉴权相关日志，THE Auth_System SHALL 不将密码明文、client_secret 明文或完整令牌写入日志。
