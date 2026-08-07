# Azure Voice Testing Admin

微软 Azure OpenAI Realtime 语音测试管理平台。基于 LiveKit + FastAPI + React 构建，支持多实例配置管理、实时语音对话测试、Token 消耗追踪和调试日志查看。

## 功能特性

- 🎙️ **实时语音对话** — 基于 Azure OpenAI Realtime API 的双向语音交互
- 📦 **多实例管理** — 支持配置多个 Azure 端点/模型/密钥，独立测试
- 🎵 **音色选择** — 支持 8 种音色切换（alloy、ash、ballad、coral、echo、sage、shimmer、verse）
- 📊 **用量统计** — 实时追踪每次会话的 Input/Output Token 消耗
- 🔍 **调试控制台** — 实时查看 WebSocket 事件流、请求响应载荷
- 📜 **会话历史** — 浏览历史对话记录，查看统计数据和日志回放
- 🐳 **Docker 一键部署** — Caddy + FastAPI + LiveKit 容器化部署

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | React 19 + TypeScript + Tailwind CSS v4 + shadcn/ui |
| 后端 | Python FastAPI + aiosqlite + livekit-agents |
| 语音 | LiveKit (自建) + Azure OpenAI Realtime (gpt-realtime-2.1) |
| 部署 | Docker Compose + Caddy (自动 HTTPS) |
| 代码质量 | pre-commit + Ruff + Commitizen |

## 快速开始（Docker 部署）

```bash
cd azure-voice-admin

# 配置环境变量
cp .env.production.example .env.production
# 编辑 .env.production 设置 LiveKit 密钥

# 构建并启动
./build.sh
docker compose up -d

# 访问
open http://localhost
```

## 本地开发

```bash
# 1. 启动 LiveKit Server
livekit-server --dev --bind 0.0.0.0

# 2. 启动后端
cd azure-voice-admin/backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8090

# 3. 启动前端
cd azure-voice-admin/frontend
pnpm install && pnpm dev
```

## 项目结构

```
├── azure-voice-admin/          # 管理系统主目录
│   ├── backend/                # FastAPI 后端
│   │   ├── app/api/            # REST API + WebSocket
│   │   ├── app/services/       # 业务逻辑层
│   │   ├── app/models/         # Pydantic 数据模型
│   │   ├── app/agent_worker.py # AI 语音 Agent（子进程）
│   │   └── tests/              # 107 个后端测试
│   ├── frontend/               # React SPA
│   │   ├── src/pages/          # 页面组件
│   │   ├── src/components/     # UI 组件
│   │   └── src/hooks/          # 自定义 Hooks
│   ├── docker-compose.yml      # Docker 编排
│   ├── Dockerfile.caddy        # Caddy + 前端构建
│   ├── Caddyfile               # 反向代理配置
│   ├── livekit.yaml            # LiveKit 服务配置
│   ├── build.sh                # 构建脚本
│   ├── deploy.sh               # 部署脚本
│   └── stop.sh                 # 停止脚本
├── .pre-commit-config.yaml     # Pre-commit 钩子
├── ruff.toml                   # Python lint 配置
└── .cz.toml                    # Commit 规范配置
```

## Commit 规范

项目使用 Conventional Commits，提交信息格式：

```
<type>(<scope>): <description>
```

类型：feat / fix / docs / style / refactor / perf / test / build / ci / chore / revert

## License

MIT
