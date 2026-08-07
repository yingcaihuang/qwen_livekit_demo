# Azure Voice Testing Admin

Azure OpenAI Realtime 语音测试管理面板 — 本地部署的 Web 管理工具。

## Docker 部署（推荐）

```bash
# 配置
cp .env.production.example .env.production
# 编辑 .env.production（默认 HTTP 模式，内网即可使用）

# 构建 & 启动
./build.sh
docker compose up -d

# 停止
./stop.sh
```

访问 `http://localhost` 即可使用。

### 服务架构

| 服务 | 端口 | 说明 |
|------|------|------|
| Caddy | :80/:443 | 反向代理 + 前端静态文件 |
| Backend | :8090 (内部) | FastAPI API + WebSocket |
| LiveKit | :7880/:7882/udp | 信令 + 音频媒体 |

### 环境变量

参见 `.env.production.example`，支持两种模式：
- **内网模式** — `SITE_DOMAIN=:80`（默认，纯 HTTP）
- **公网模式** — `SITE_DOMAIN=your-domain.com`（Caddy 自动签发 HTTPS）

## 功能

- 多 Azure 实例管理（不同 endpoint/key/model）
- 实时语音对话（8 种音色可选）
- Token 用量实时追踪
- Debug Console 实时日志
- 会话历史管理

## 本地开发

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8090
```

### 前端

```bash
cd frontend
pnpm install
pnpm dev
```

前端开发服务器 http://localhost:5173，API 代理到 http://localhost:8090。

## 项目结构

```
azure-voice-admin/
├── backend/
│   ├── app/
│   │   ├── api/              # REST API + WebSocket 端点
│   │   ├── models/           # Pydantic 数据模型
│   │   ├── services/         # 业务逻辑（Session, Instance, ProcessManager, LogBroadcaster）
│   │   ├── agent_worker.py   # LiveKit Agent Worker（Azure OpenAI Realtime）
│   │   ├── main.py           # FastAPI 应用入口
│   │   ├── database.py       # SQLite 异步连接管理
│   │   └── schema.sql        # 数据库 Schema
│   ├── tests/                # 107 个测试
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── pages/            # Dashboard, Instances, VoiceSession, History
│   │   ├── components/       # UI 组件（shadcn/ui）
│   │   ├── hooks/            # useLiveKit, useSessionLogs, useApi
│   │   └── types/            # TypeScript 类型定义
│   └── package.json
├── docker-compose.yml        # 3 服务编排
├── Dockerfile.caddy          # Multi-stage: pnpm build + Caddy
├── Caddyfile                 # 反向代理规则
├── livekit.yaml              # LiveKit Server 配置
├── build.sh / deploy.sh / stop.sh
└── .env.production.example
```

## 运行测试

```bash
cd backend
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
