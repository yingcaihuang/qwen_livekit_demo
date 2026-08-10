# Azure Voice Testing Admin

Azure OpenAI 多模态测试管理平台 — 支持语音对话、文本聊天、图片生成，内置用户认证与 RBAC 权限管理。

## 快速开始

```bash
# 1. 配置环境变量
cp .env.production.example .env.production

# 2. 构建 & 启动
./build.sh
docker compose up -d
```

访问 `http://localhost` 即可使用。

### 默认管理员账号

| 用户名 | 密码 | 说明 |
|--------|------|------|
| `admin` | `ChangeMe@2024` | 首次登录需强制修改密码 |

可通过环境变量 `SEED_ADMIN_USERNAME` / `SEED_ADMIN_PASSWORD` 覆盖默认值。

## 功能

### AI 多模态测试

- **语音对话** — Azure OpenAI Realtime 实时语音（8 种音色可选）
- **Chat Playground** — 文本对话，支持 Markdown / 代码高亮 / 数学公式 / Mermaid 图表渲染
- **Image Generation** — 图片生成，支持参考图上传

### 实例管理

- 多 Azure 实例配置（不同 endpoint / api_key / deployment）
- 实例类型区分：voice / chat / image

### 用户认证与授权

- 本地账号登录（bcrypt 密码哈希，服务端 session）
- OIDC SSO 集成（Authentik / Keycloak 等）
- SAML 2.0 SP 支持
- SCIM v2 用户自动同步
- 登录失败限流（60 秒内 5 次失败锁定）
- 首次登录强制修改密码

### RBAC 四级角色

| 角色 | 权限范围 |
|------|----------|
| `super_admin` | 全部权限（用户管理、角色管理、SSO 配置） |
| `admin` | 实例读写、会话运行、查看所有资源、Dashboard |
| `tester` | 实例读写、会话运行、Chat/Image 使用、Dashboard |
| `viewer` | 只读（查看实例和 Dashboard） |

### 用户管理

- 管理员创建 / 禁用 / 删除用户
- 管理员重置用户密码（随机密码自动复制到剪贴板）
- SSO 用户自动创建与组映射角色同步
- 手动角色覆盖（阻止 SSO 自动更新）

### Dashboard & 统计

- Token 用量统计（输入 / 输出）
- 按实例 / 类型分类统计
- 会话历史（语音 / Chat / 图片）

## Docker 部署

### 服务架构

| 服务 | 端口 | 说明 |
|------|------|------|
| Caddy | :80 / :443 | 反向代理 + 前端静态文件 |
| Backend | :8090 (内部) | FastAPI API + WebSocket |
| LiveKit | :7880 / :7882/udp | 信令 + 音频媒体 |

### 环境变量

参见 `.env.production.example`，支持两种模式：

- **内网模式** — `SITE_DOMAIN=:80`（默认，纯 HTTP）
- **公网模式** — `SITE_DOMAIN=your-domain.com`（Caddy 自动签发 HTTPS）

```bash
# 停止服务
./stop.sh
```

## 本地开发

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8090
```

### 前端

```bash
cd frontend
pnpm install
pnpm dev
```

前端开发服务器 http://localhost:5173，API 代理到 http://localhost:8090。

## 运行测试

```bash
# 后端测试（271 个）
cd backend
source .venv/bin/activate
pytest

# 前端测试（58 个）
cd frontend
pnpm test
```

## 项目结构

```
azure-voice-admin/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py            # 登录/登出/会话
│   │   │   ├── admin_users.py     # 用户管理（CRUD）
│   │   │   ├── admin_roles.py     # 角色分配
│   │   │   ├── admin_sso.py       # SSO 配置管理
│   │   │   ├── admin_saml.py      # SAML 配置管理
│   │   │   ├── sso.py             # OIDC 登录回调
│   │   │   ├── saml.py            # SAML ACS/SLO 端点
│   │   │   ├── scim.py            # SCIM v2 用户同步
│   │   │   ├── chat.py            # Chat Playground API
│   │   │   ├── images.py          # Image Generation API
│   │   │   ├── instances.py       # 实例 CRUD
│   │   │   ├── sessions.py        # 语音会话管理
│   │   │   ├── dashboard.py       # 统计 Dashboard
│   │   │   ├── history.py         # 会话历史
│   │   │   ├── deps.py            # 依赖注入（认证守卫）
│   │   │   └── websockets.py      # WebSocket 端点
│   │   ├── services/
│   │   │   ├── auth_service.py    # 密码哈希/会话/限流
│   │   │   ├── rbac.py            # RBAC 角色→能力映射
│   │   │   ├── oidc_service.py    # OIDC 协议实现
│   │   │   ├── saml_service.py    # SAML 2.0 SP 实现
│   │   │   ├── provisioning_service.py  # SCIM 用户同步
│   │   │   ├── crypto_service.py  # 密钥加密存储
│   │   │   ├── chat_service.py    # Chat 业务逻辑
│   │   │   ├── image_service.py   # 图片生成逻辑
│   │   │   ├── instance_service.py
│   │   │   ├── session_service.py
│   │   │   ├── dashboard_service.py
│   │   │   ├── process_manager.py # LiveKit Agent 进程管理
│   │   │   └── log_broadcaster.py # 实时日志广播
│   │   ├── agent_worker.py        # LiveKit Agent Worker
│   │   ├── main.py                # FastAPI 应用入口
│   │   ├── config.py              # 环境变量配置
│   │   ├── database.py            # SQLite 异步连接 + 迁移
│   │   └── schema.sql             # 数据库 Schema
│   ├── tests/                     # 271 个测试
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── LoginPage.tsx          # 登录页
│   │   │   ├── ChangePasswordPage.tsx # 强制改密页
│   │   │   ├── DashboardPage.tsx      # 统计面板
│   │   │   ├── InstancesPage.tsx      # 实例列表
│   │   │   ├── VoiceSessionPage.tsx   # 语音对话
│   │   │   ├── ChatPlaygroundPage.tsx # 文本聊天
│   │   │   ├── ImagePlaygroundPage.tsx# 图片生成
│   │   │   ├── HistoryPage.tsx        # 会话历史
│   │   │   └── admin/
│   │   │       ├── UsersPage.tsx      # 用户管理
│   │   │       ├── SsoConfigPage.tsx  # SSO 配置
│   │   │       └── GroupMappingsPage.tsx  # 组映射
│   │   ├── components/            # UI 组件（shadcn/ui）
│   │   ├── hooks/                 # useLiveKit, useSessionLogs, useApi
│   │   ├── lib/                   # 工具函数
│   │   └── types/                 # TypeScript 类型定义
│   └── package.json
├── docker-compose.yml             # 3 服务编排
├── Dockerfile.caddy               # Multi-stage: pnpm build + Caddy
├── Caddyfile                      # 反向代理规则
├── livekit.yaml                   # LiveKit Server 配置
├── build.sh / deploy.sh / stop.sh
└── .env.production.example
```

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.12 / FastAPI / aiosqlite / bcrypt |
| 前端 | React 18 / TypeScript / Vite / shadcn/ui / TailwindCSS |
| 数据库 | SQLite（WAL 模式，零外部依赖） |
| 语音 | LiveKit Server + LiveKit Agent SDK |
| 反向代理 | Caddy（自动 HTTPS） |
| 容器化 | Docker Compose |
