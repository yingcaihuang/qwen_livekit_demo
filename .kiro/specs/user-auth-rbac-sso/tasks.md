# Implementation Plan: 用户鉴权系统（user-auth-rbac-sso）

## Overview
按后端 → 前端顺序增量实现：先落地数据层（schema + 幂等迁移 + Seed_Admin 播种），再实现 RBAC 与会话/加密等核心服务，随后本地登录与 OIDC SSO，接着为现有接口挂权限守卫并加管理后台，最后完成前端登录页、路由守卫与后台页面并整体接线。测试作为各父任务下的子任务，标 `*` 者为可选。后端用 `pytest`/`hypothesis`，前端用 `vitest`；后端语言为 Python，前端为 TypeScript/React（与设计一致，无需另选语言）。

验证命令：
- 后端（在 `azure-voice-admin/backend`）：`.venv/bin/python -m pytest -q`
- 前端（在 `azure-voice-admin/frontend`）：`node_modules/.bin/tsc -b && node_modules/.bin/vite build --outDir ../backend/static && node_modules/.bin/vitest run`（不要使用 pnpm）

## Tasks
- [x] 1. 数据层：新增表结构与幂等迁移
  - [x] 1.1 在 `app/schema.sql` 追加鉴权相关表
    - 追加 `users`、`user_roles`、`group_role_mappings`、`sso_config`、`auth_sessions`、`login_attempts`、`oidc_login_state` 及索引，全部使用 `CREATE TABLE IF NOT EXISTS`
    - _Requirements: 2.1, 5.1, 6.1, 9.5, 10.2, 12.1_
  - [x] 1.2 在 `app/database.py::_migrate()` 增加补列与播种逻辑
    - 为 `instances`、`sessions`、`image_generations` 三张表幂等补充可空列 `created_by`（`PRAGMA table_info` 检测后 `ALTER TABLE ADD COLUMN`）
    - 播种 `sso_config` 单例行（`INSERT OR IGNORE (id=1)`，`login_button_enabled=0`）
    - _Requirements: 7.5.1, 7.4, 9.6, 3.1_
  - [ ]* 1.3 编写迁移幂等属性测试 `tests/test_auth_migration.py`
    - 参照 `tests/test_migration.py`，验证三张表（instances, sessions, image_generations）补列与 `sso_config` 播种多次 `init_db` 幂等、旧数据保留
    - _Requirements: 3.1, 7.5.1, 9.6_

- [x] 2. 核心服务：RBAC、加密、会话与密码
  - [x] 2.1 实现 `app/services/rbac.py`
    - 定义 `CAPABILITIES`（含 `resource:read:all` 代替 `history:read:own/all`）、`ROLE_CAPABILITIES` 四角色映射与 `capabilities_for(roles)` 并集函数
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 7.5_
  - [ ]* 2.2 编写 RBAC 属性与示例测试
    - **属性 1：能力集合为角色能力并集**
    - **Validates: Requirements 6.7, 6.3, 6.4, 6.5, 6.6**
    - 并以示例断言四角色固定能力集合（6.1–6.6）
  - [x] 2.3 实现 `app/services/crypto_service.py`
    - 从环境变量 `AUTH_SECRET_KEY` 读取密钥，提供对称 `encrypt`/`decrypt`
    - _Requirements: 9.2, 13.4_
  - [ ]* 2.4 编写加密 round-trip 属性测试
    - **属性 13：可逆加密 round-trip 且落库非明文**
    - **Validates: Requirements 9.2, 13.4**
  - [x] 2.5 实现密码哈希与会话管理（`app/services/auth_service.py`）
    - bcrypt/argon2 哈希与校验；会话签发（随机 token、`expires_at` 默认 8h、`csrf_token`）、`load_session`、失效、按 user 批量失效
    - 更新 `pyproject.toml` 依赖：`passlib[bcrypt]`（或 `argon2-cffi`）、`cryptography`
    - _Requirements: 2.3, 2.5, 11.4, 12.1, 12.2, 12.3_
  - [ ]* 2.6 编写密码哈希属性测试
    - **属性 3：密码哈希单向可验证**
    - **Validates: Requirements 2.3**
  - [ ]* 2.7 编写会话过期属性测试
    - **属性 17：会话过期后拒绝**
    - **Validates: Requirements 12.1, 12.2**

- [x] 3. 鉴权依赖与 Seed_Admin 播种
  - [x] 3.1 实现 `app/api/deps.py` 鉴权依赖
    - `get_current_user`（读 Cookie → 校验会话 → 加载用户与角色）、`require_permission(cap)`（403）、`CurrentUser` 模型
    - _Requirements: 7.1, 7.2, 7.3_
  - [ ]* 3.2 编写接口守卫三态属性测试
    - **属性 2：接口守卫按能力三态判定**
    - **Validates: Requirements 7.1, 7.2, 7.3, 9.7, 10.4, 11.3**
  - [x] 3.3 在 `_migrate()` 中实现 Seed_Admin 播种
    - 若无任何 `super_admin`，按 `SEED_ADMIN_USERNAME`/`SEED_ADMIN_PASSWORD` 创建本地账号（缺密码则随机生成并 `logger.warning` 输出一次），置 `must_change_password=1` 并写 `user_roles`
    - _Requirements: 3.1, 3.2_
  - [ ]* 3.4 编写 Seed_Admin 幂等测试
    - 多次 `init_db` 不重复创建、已存在 super_admin 时不覆盖
    - _Requirements: 3.1_

- [x] 4. 检查点 —— 确保数据层与核心服务测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. 本地登录与会话接口
  - [x] 5.1 实现登录限流（`app/services/auth_service.py`）
    - 基于 `login_attempts` 记录失败并在 60s 窗口累计 5 次后 60s 内返回限流
    - _Requirements: 2.4_
  - [ ]* 5.2 编写限流属性测试
    - **属性 5：登录失败限流阈值**
    - **Validates: Requirements 2.4**
  - [x] 5.3 实现 `app/api/auth.py` 认证接口
    - `POST /api/auth/login`（成功下发 httpOnly+Secure+SameSite Cookie，统一失败提示，禁用账号拒绝）、`POST /api/auth/logout`、`GET /api/auth/me`（返回身份/角色/能力）
    - _Requirements: 2.1, 2.2, 2.5, 2.6, 12.3, 12.4_
  - [ ]* 5.4 编写登录不泄露存在性属性测试
    - **属性 4：错误登录不泄露账号存在性**
    - **Validates: Requirements 2.2**
  - [x] 5.5 实现改密接口 `POST /api/auth/change-password`
    - 校验新密码长度≥12，成功后清除 `must_change_password`
    - _Requirements: 3.3, 3.4, 3.5_
  - [ ]* 5.6 编写密码强度属性测试
    - **属性 6：密码强度阈值**
    - **Validates: Requirements 3.4, 3.5**
  - [ ]* 5.7 编写会话与登出示例测试
    - Cookie 属性、登出失效清 Cookie、登录响应负载
    - _Requirements: 2.5, 12.3, 12.4_

- [x] 6. OIDC SSO 登录与自动开通
  - [x] 6.1 实现 `app/services/oidc_service.py`
    - `discover()` 从 discovery 获取端点；`build_authorization_url`（state/nonce/PKCE S256）；`exchange_code`；`verify_id_token`（JWKS 验签 + iss/aud/nonce）；`fetch_userinfo`
    - 更新 `pyproject.toml`：`python-jose[cryptography]`（或 `PyJWT`+`cryptography`）
    - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.6, 9.4_
  - [ ]* 6.2 编写 OIDC 登录态生成属性测试
    - **属性 7：OIDC 登录态生成唯一且 PKCE 一致**
    - **Validates: Requirements 4.1**
  - [ ]* 6.3 编写 ID Token 校验属性测试
    - **属性 9：ID Token 校验拒绝篡改**
    - **Validates: Requirements 4.4, 4.5**
  - [x] 6.4 实现 `app/services/provisioning_service.py`
    - 依 subject 自动开通唯一 SSO_User；依 groups + `group_role_mappings` 计算角色，无匹配则 `viewer`；再次登录按当前 groups 更新
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - [ ]* 6.5 编写自动开通唯一性属性测试
    - **属性 10：SSO 用户自动开通唯一性**
    - **Validates: Requirements 5.1**
  - [ ]* 6.6 编写角色映射收敛属性测试
    - **属性 11：角色由当前分组映射收敛决定**
    - **Validates: Requirements 5.2, 5.3, 5.4**
  - [x] 6.7 实现 `app/api/sso.py` 端点
    - `GET /api/auth/sso/login`（存 `oidc_login_state` 并 302，开关关闭时拒绝）、`GET /api/auth/sso/callback`（校验 state → 换 token → 验签 → userinfo → 开通 → 建会话下发 Cookie）、`GET /api/auth/sso/public-config`（仅返回 `login_button_enabled`）
    - _Requirements: 4.1, 4.2, 4.3, 4.6, 4.7, 5.5, 1.3, 1.4_
  - [ ]* 6.8 编写回调 state 校验属性测试
    - **属性 8：OIDC 回调 state 校验**
    - **Validates: Requirements 4.2, 4.3**

- [x] 7. 检查点 —— 确保登录与 SSO 测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. 管理后台接口
  - [x] 8.1 实现 `app/api/admin_sso.py`（`sso:manage`）
    - `GET/PUT /api/admin/sso-config`：保存时加密 client_secret、返回时脱敏（仅 `client_secret_set`）、持久化入口开关
    - _Requirements: 9.1, 9.2, 9.3, 9.5, 9.6, 9.7_
  - [ ]* 8.2 编写 SSO 配置脱敏属性测试
    - **属性 14：SSO 配置返回脱敏**
    - **Validates: Requirements 9.3, 13.5**
  - [ ]* 8.3 编写入口开关持久化属性测试
    - **属性 19：登录页 SSO 入口显隐等于开关**（后端侧：public-config 返回值与写入一致）
    - **Validates: Requirements 1.3, 1.4, 9.6**
  - [x] 8.4 实现 `app/api/admin_roles.py`（`role:manage`）
    - `GET/POST/PUT/DELETE /api/admin/group-mappings`：校验角色取值合法
    - _Requirements: 10.1, 10.2, 10.3, 10.4_
  - [ ]* 8.5 编写组映射角色校验属性测试
    - **属性 15：组映射角色取值校验**
    - **Validates: Requirements 10.3**
  - [x] 8.6 实现 `app/api/admin_users.py`（`user:manage`）
    - 列表/创建（哈希+强制改密）/启停/改角色；禁用时批量失效该用户会话
    - _Requirements: 11.1, 11.2, 11.3, 11.4_
  - [ ]* 8.7 编写禁用用户会话失效属性测试
    - **属性 16：禁用用户会话立即失效**
    - **Validates: Requirements 11.4, 2.6**

- [x] 9. 为现有接口挂权限守卫并接线后端
  - [x] 9.1 为现有路由补 `require_permission` 守卫与资源多租户隔离
    - `instances`（read/write）、`sessions`（session:run）、`chat`（chat:use）、`images`（image:use）、`dashboard`（dashboard:read）
    - 所有列表/详情/更新/删除接口加入 owner 过滤逻辑：无 `resource:read:all` 时仅操作 `created_by` 等于当前用户的记录，有则不过滤
    - 创建接口写入 `created_by = user.id`；按 ID 访问他人资源返回 404（不泄露存在性）
    - dashboard 统计数据按 `created_by` 过滤（admin/super_admin 看全局）
    - _Requirements: 7.1, 7.2, 7.3, 7.5.1, 7.5.2, 7.5.3, 7.5.4, 7.5.5, 7.5.6_
  - [x] 9.2 实现资源多租户隔离过滤
    - 在所有资源接口（instances、sessions、image_generations、chat、dashboard、history）统一实现多租户隔离：无 `resource:read:all` 时按 `created_by` 过滤；有则返回全部
    - chat session 创建时写入 `created_by`，后续消息的归属继承自 session
    - _Requirements: 7.5.1, 7.5.2, 7.5.3, 7.5.4, 7.5.5, 7.5.6_
  - [ ]* 9.3 编写资源多租户隔离属性测试
    - **属性 12：资源按 resource:read:all 隔离过滤**
    - **属性 21：资源多租户隔离（创建归属、列表过滤、单资源 404）**
    - **Validates: Requirements 7.4, 7.5.1, 7.5.2, 7.5.3, 7.5.4, 7.5.5, 7.5.6**
  - [x] 9.4 在 `app/main.py` 注册路由、收紧 CORS、实现 CSRF 校验
    - 注册 `auth/sso/admin_*` 路由；CORS 由环境变量可信来源列表替代 `*`；对状态变更接口校验双提交 CSRF 令牌；保持 `/api/health` 与登录/回调公开
    - _Requirements: 7.6, 13.1, 13.3, 13.5_
  - [ ]* 9.5 编写 CSRF 校验属性测试
    - **属性 18：CSRF 令牌校验状态变更请求**
    - **Validates: Requirements 13.3**

- [x] 10. 检查点 —— 确保后端全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. 前端鉴权基础设施
  - [x] 11.1 实现 `components/auth/AuthProvider.tsx` 与 `useAuth`
    - 启动请求 `/api/auth/me`，暴露 user/roles/capabilities/loading
    - _Requirements: 8.1, 12.4_
  - [x] 11.2 改造 `hooks/useApi.ts` 与全局 fetch
    - 所有请求加 `credentials: 'include'`，收到 401 时跳转 `/login`
    - _Requirements: 13.2, 8.4_
  - [x] 11.3 实现 `components/auth/ProtectedRoute.tsx`
    - 未登录跳 `/login`，缺能力重定向默认页
    - _Requirements: 8.1, 8.2, 1.1_
  - [ ]* 11.4 编写路由守卫属性测试
    - **属性 20：未认证访问受保护前端路由重定向**
    - **Validates: Requirements 1.1, 8.4**

- [x] 12. 登录页与后台页面
  - [x] 12.1 实现 `pages/LoginPage.tsx`
    - 上方本地表单（加载态禁用按钮）；下方按 `/api/auth/sso/public-config` 的 `login_button_enabled` 显隐"统一认证入口"；背景亮度≤95%
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6_
  - [ ]* 12.2 编写登录页 SSO 入口显隐测试
    - **属性 19：登录页 SSO 入口显隐等于开关**（前端侧渲染）
    - **Validates: Requirements 1.3, 1.4**
  - [x] 12.3 实现首次强制改密页/流程
    - 命中 `must_change_password` 时引导改密后再访问其他资源
    - _Requirements: 3.3_
  - [x] 12.4 实现后台页面：用户管理、组映射、SSO 配置
    - `pages/admin/UsersPage.tsx`、`GroupMappingsPage.tsx`、`SsoConfigPage.tsx`，client_secret 仅显示"是否已设置"
    - _Requirements: 9.1, 9.5, 10.1, 11.1_

- [x] 13. 前端接线与导航
  - [x] 13.1 改造 `App.tsx` 路由
    - 新增 `/login` 与 `/admin/*`，其余路由包裹 `ProtectedRoute` 并标注所需能力
    - _Requirements: 8.1, 8.2_
  - [x] 13.2 改造 `Sidebar` 能力驱动显隐
    - 依 capabilities 隐藏无权入口，展示后台入口（sso/user/role manage）
    - _Requirements: 8.3, 8.5_
  - [ ]* 13.3 编写导航显隐测试
    - 对不同能力集合断言入口存在性（属性 8.3/8.5 的前端实例）
    - _Requirements: 8.3, 8.5_

- [x] 14. 最终检查点 —— 确保前后端测试与构建通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes
- 标记 `*` 的子任务为可选（测试），可为快速 MVP 跳过；核心实现子任务不得跳过。
- 每个任务引用具体需求编号以便追溯；属性测试子任务显式引用设计文档中的属性编号（1–21）。
- 检查点用于增量验证。属性测试用 `hypothesis`（后端，`max_examples>=100`）/`vitest`（前端）；单元测试覆盖固定映射与边界。
- 外部 Authentik 交互（userinfo/discovery）在测试中使用 mock/示例，不做真实网络往返。
- 资源多租户隔离（需求 7.5）贯穿任务 1.2（补列）、9.1（权限守卫+owner 过滤）、9.2（统一隔离实现）、9.3（属性测试），是核心安全原则。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "2.3"] },
    { "id": 2, "tasks": ["1.3", "2.2", "2.4", "2.5"] },
    { "id": 3, "tasks": ["2.6", "2.7", "3.1", "3.3"] },
    { "id": 4, "tasks": ["3.2", "3.4", "5.1", "6.1", "6.4"] },
    { "id": 5, "tasks": ["5.2", "5.3", "5.5", "6.2", "6.3", "6.5", "6.6", "6.7"] },
    { "id": 6, "tasks": ["5.4", "5.6", "5.7", "6.8", "8.1", "8.4", "8.6"] },
    { "id": 7, "tasks": ["8.2", "8.3", "8.5", "8.7", "9.1"] },
    { "id": 8, "tasks": ["9.2", "9.4"] },
    { "id": 9, "tasks": ["9.3", "9.5", "11.1", "11.2", "11.3"] },
    { "id": 10, "tasks": ["11.4", "12.1", "12.3", "12.4"] },
    { "id": 11, "tasks": ["12.2", "13.1", "13.2"] },
    { "id": 12, "tasks": ["13.3"] }
  ]
}
```
