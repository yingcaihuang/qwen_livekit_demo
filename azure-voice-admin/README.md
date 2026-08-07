# Azure Voice Testing Admin

Azure OpenAI Realtime 语音测试管理面板 - 本地部署的 Web 管理工具，帮助开发者管理多个 Azure OpenAI Realtime API 实例配置、发起实时语音对话测试、追踪 Token 消耗和费用、查看调试日志。

## 快速开始

### 1. 安装后端依赖

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

### 2. 安装前端依赖

```bash
cd frontend
pnpm install
```

### 3. 配置环境变量

复制后端环境变量模板并填写配置：

```bash
cd backend
cp .env.example .env
```

编辑 `.env` 文件，设置以下变量：

- `LIVEKIT_URL` - LiveKit 服务器 WebSocket 地址（默认 `ws://localhost:7880`）
- `LIVEKIT_API_KEY` - LiveKit API Key
- `LIVEKIT_API_SECRET` - LiveKit API Secret
- `DB_PATH` - SQLite 数据库文件路径（默认 `./data.db`）
- `PORT` - 服务端口（默认 `8090`）

### 4. 构建前端

```bash
cd frontend
pnpm build
```

构建产物会输出到 `backend/static/` 目录，由 FastAPI 在生产模式下直接托管。

### 5. 启动系统

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8090
```

启动后访问 http://localhost:8090 即可使用管理面板。

## 开发模式

前后端分别启动，前端开发服务器会自动代理 API 请求到后端：

```bash
# 终端 1: 启动后端
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8090

# 终端 2: 启动前端开发服务器
cd frontend
pnpm dev
```

前端开发服务器默认运行在 http://localhost:5173，API 请求会代理到 http://localhost:8090。

## 项目结构

```
azure-voice-admin/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI 路由
│   │   ├── models/       # Pydantic 数据模型
│   │   ├── services/     # 业务逻辑层
│   │   ├── main.py       # 应用入口
│   │   ├── database.py   # 数据库管理
│   │   └── schema.sql    # 数据库 Schema
│   ├── tests/            # 后端测试
│   ├── static/           # 前端构建产物（自动生成）
│   └── pyproject.toml    # 后端项目配置
└── frontend/
    ├── src/
    │   ├── components/   # React 组件
    │   ├── pages/        # 页面组件
    │   ├── hooks/        # 自定义 Hooks
    │   ├── lib/          # 工具函数
    │   └── types/        # TypeScript 类型定义
    ├── package.json
    └── vite.config.ts
```
