# Azure Voice Testing Admin

Azure OpenAI 多模态测试管理平台 — 支持语音对话、文本聊天、图片生成、实时翻译、实时转录，内置用户认证与 RBAC 权限管理。

## 系统截图

### Dashboard

![Dashboard](azure-voice-admin/docs/screenshots/dashboard.png)

### 实例管理

![实例管理](azure-voice-admin/docs/screenshots/instance-list.png)

### 会话历史

![会话历史列表](azure-voice-admin/docs/screenshots/historylist.png)

### Chat 对话详情

![Chat 对话](azure-voice-admin/docs/screenshots/history-chat.png)

### 语音会话详情

![语音会话](azure-voice-admin/docs/screenshots/history-voice.png)

### 图片生成详情

![图片生成](azure-voice-admin/docs/screenshots/histotry-image2.png)

### SSO 组映射

![SSO 组映射](azure-voice-admin/docs/screenshots/authentik-groups.png)

## 功能特性

- 🎙️ **实时语音对话** — Azure OpenAI Realtime API 双向语音交互（8 种音色）
- 💬 **Chat Playground** — 文本对话，Markdown / 代码高亮 / 数学公式 / Mermaid 图表
- 🎨 **Image Generation** — 图片生成与编辑，支持多张参考图（最多 10 张）
- 🌐 **实时翻译** — Azure Realtime Translate 多语言实时翻译
- 📝 **实时转录** — Azure Realtime Whisper 语音转文字
- 📦 **多实例管理** — 多个 Azure 端点 / 密钥 / 模型独立配置
- 📊 **Dashboard 统计** — Token 用量追踪，按实例 / 类型分类
- 📜 **会话历史** — 语音 / Chat / 图片 / 翻译 / 转录会话记录与详情回放
- 🔐 **用户认证** — 本地账号 + OIDC SSO + SAML 2.0 + SCIM v2
- 👥 **RBAC 权限** — 四级角色（super_admin / admin / tester / viewer）
- 🐳 **Docker 一键部署** — Caddy + FastAPI + LiveKit 容器化

## 部署方式

### 方式一：使用预构建镜像（推荐）

直接从 GitHub Container Registry 拉取预构建镜像，无需本地编译：

```bash
# 1. 克隆仓库（只需要配置文件）
git clone https://github.com/yingcaihuang/qwen_livekit_demo.git
cd qwen_livekit_demo/azure-voice-admin

# 2. 配置环境变量
cp .env.production.example .env.production
# 编辑 .env.production 填入你的 LiveKit 密钥等配置

# 3. 启动服务
docker compose -f docker-compose.ghcr.yml up -d
```

镜像地址：
| 镜像 | 说明 |
|------|------|
| `ghcr.io/yingcaihuang/azure-voice-admin-caddy:latest` | 前端 + Caddy 反向代理 |
| `ghcr.io/yingcaihuang/azure-voice-admin-backend:latest` | Python 后端 API |

> 镜像在每次 `main` 分支有 `azure-voice-admin/` 目录变更时自动构建推送。

### 方式二：本地构建

适合需要自定义修改的场景：

```bash
cd azure-voice-admin

# 配置
cp .env.production.example .env.production

# 构建 & 启动
./build.sh
docker compose up -d
```

### 公网部署

对于公网部署，需要额外配置域名和 HTTPS：

```bash
# .env.production 中设置：
SITE_DOMAIN=your-domain.com          # Caddy 自动申请 HTTPS 证书
LIVEKIT_PUBLIC_URL=wss://rtc.your-domain.com:7880  # 客户端 WebSocket 连接地址
```

### 首次登录

访问部署地址，使用默认管理员账号：

| 用户名 | 密码 | 说明 |
|--------|------|------|
| `admin` | `ChangeMe@2024` | 首次登录需强制修改密码 |

### 更新版本

```bash
# 预构建镜像方式
docker compose -f docker-compose.ghcr.yml pull
docker compose -f docker-compose.ghcr.yml up -d

# 本地构建方式
git pull
./build.sh
docker compose up -d
```

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | React 19 + TypeScript + Vite + shadcn/ui + TailwindCSS v4 |
| 后端 | Python 3.12 + FastAPI + aiosqlite + bcrypt |
| 数据库 | SQLite（WAL 模式，零外部依赖） |
| 语音 | LiveKit Server + LiveKit Agent SDK |
| 反向代理 | Caddy（自动 HTTPS） |
| 容器化 | Docker Compose |
| CI/CD | GitHub Actions → GitHub Container Registry |
| 代码质量 | pre-commit + Ruff + Commitizen |

## 本地开发

```bash
# 后端
cd azure-voice-admin/backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8090

# 前端
cd azure-voice-admin/frontend
pnpm install && pnpm dev
```

## 测试

```bash
# 后端（271 个测试）
cd azure-voice-admin/backend && pytest

# 前端（58 个测试）
cd azure-voice-admin/frontend && pnpm test
```

## 项目结构

```
├── .github/workflows/
│   └── docker-publish.yml      # CI: 自动构建推送镜像
├── azure-voice-admin/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── api/            # REST API + WebSocket
│   │   │   ├── services/       # 业务逻辑（Auth, RBAC, SSO, SAML, Chat, Image）
│   │   │   ├── models/         # Pydantic 数据模型
│   │   │   ├── agent_worker.py # LiveKit AI Agent（语音）
│   │   │   ├── translate_worker.py  # 实时翻译 Worker
│   │   │   ├── transcribe_worker.py # 实时转录 Worker
│   │   │   ├── database.py     # SQLite + 迁移
│   │   │   └── schema.sql      # 数据库 Schema
│   │   └── tests/              # 271 个测试
│   ├── frontend/
│   │   ├── src/pages/          # 页面组件
│   │   ├── src/components/     # UI 组件
│   │   └── src/hooks/          # 自定义 Hooks
│   ├── docker-compose.yml      # 本地构建部署
│   ├── docker-compose.ghcr.yml # 预构建镜像部署
│   ├── Caddyfile
│   ├── livekit.yaml
│   └── build.sh / stop.sh
├── .pre-commit-config.yaml
├── ruff.toml
└── .cz.toml
```

## Commit 规范

Conventional Commits：`<type>(<scope>): <description>`

类型：feat / fix / docs / style / refactor / perf / test / build / ci / chore

## License

MIT
