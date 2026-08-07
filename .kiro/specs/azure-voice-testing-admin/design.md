# Design Document: Azure Realtime Voice Testing Management System

## Overview

本系统是一个本地部署的 Azure OpenAI Realtime 语音测试管理面板，采用前后端分离架构。前端使用 React + TypeScript + Tailwind CSS + shadcn/ui 构建单页应用；后端使用 Python FastAPI 提供 REST API 和 WebSocket 实时通信；语音流转通过 LiveKit 自托管服务器和 livekit-agents 框架实现。

核心设计目标：
- 支持管理多个 Azure OpenAI Realtime 实例配置
- 每个会话独立生成 Agent Worker 子进程，隔离凭据和运行环境
- 实时调试日志通过 WebSocket 推送到前端
- 所有数据持久化到单一 SQLite 数据库文件

## Architecture

### 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户浏览器                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              React SPA (Vite + TypeScript)                │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │   │
│  │  │ Dashboard │  │Instances │  │Voice Chat│  │History │  │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └────────┘  │   │
│  └────────────┬────────────────────┬────────────────────────┘   │
│               │ REST API           │ WebSocket + LiveKit SDK     │
└───────────────┼────────────────────┼────────────────────────────┘
                │                    │
┌───────────────┼────────────────────┼────────────────────────────┐
│               ▼                    ▼                             │
│  ┌─────────────────────────────────────────────────────┐        │
│  │           FastAPI Server (port 8090)                 │        │
│  │  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  │        │
│  │  │ REST API │  │ WS /ws/logs  │  │Process Mgr   │  │        │
│  │  │ /api/*   │  │ (debug logs) │  │(spawn agents)│  │        │
│  │  └──────────┘  └──────────────┘  └──────────────┘  │        │
│  └──────────┬──────────────────────────────┬───────────┘        │
│             │                              │                     │
│             ▼                              ▼                     │
│  ┌──────────────────┐         ┌─────────────────────────┐       │
│  │  SQLite Database  │         │   Agent Worker (子进程)   │      │
│  │  - instances      │         │  ┌─────────────────────┐│      │
│  │  - sessions       │         │  │ livekit-agents      ││      │
│  │  - session_logs   │         │  │ + openai realtime   ││      │
│  └──────────────────┘         │  └─────────┬───────────┘│      │
│                                └────────────┼────────────┘       │
│                                             │                    │
└─────────────────────────────────────────────┼────────────────────┘
                                              │
                ┌─────────────────────────────┼──────────┐
                │         LiveKit Server       │          │
                │  ┌──────────────────────────┼──────┐   │
                │  │       Room (per session)  ▼      │   │
                │  │  [User Track] ←──→ [Agent Track] │   │
                │  └─────────────────────────────────┘   │
                └────────────────────────────────────────┘
                                              │
                                              ▼
                ┌────────────────────────────────────────┐
                │     Azure OpenAI Realtime API          │
                │  (WebSocket wss://...openai.azure.com) │
                └────────────────────────────────────────┘
```

### 数据流说明

1. **创建会话流**：Web_UI → POST /api/sessions → FastAPI 创建 LiveKit 房间 → 生成 Token → 返回给前端 → 同时 spawn Agent Worker 子进程
2. **语音流**：用户浏览器 ←→ LiveKit Server ←→ Agent Worker ←→ Azure OpenAI Realtime
3. **日志流**：Agent Worker → stdout/pipe → FastAPI → WebSocket → Web_UI
4. **Token 统计流**：Agent Worker 解析 `response.done` 事件中的 usage → 通过内部 HTTP 上报给 FastAPI → 写入 SQLite

## Components and Interfaces

### 后端组件

#### 1. FastAPI 主应用 (`backend/app/main.py`)

应用入口，负责：
- 注册路由（REST API + WebSocket）
- 初始化数据库连接
- 启动时执行健康检查（LiveKit 可达性）
- 托管前端静态文件（生产模式）

#### 2. Instance API (`backend/app/api/instances.py`)

```python
# REST API 接口
GET    /api/instances          # 列出所有实例（API key 已脱敏）
POST   /api/instances          # 创建实例
GET    /api/instances/{id}     # 获取实例详情
PUT    /api/instances/{id}     # 更新实例
DELETE /api/instances/{id}     # 删除实例（有活跃会话时拒绝）
```

#### 3. Session API (`backend/app/api/sessions.py`)

```python
# REST API 接口
GET    /api/sessions                    # 会话历史列表（支持分页和筛选）
POST   /api/sessions                    # 创建新会话（启动房间+Agent）
GET    /api/sessions/{id}               # 会话详情（含 token 统计）
DELETE /api/sessions/{id}               # 删除会话记录
POST   /api/sessions/{id}/stop          # 终止活跃会话

# WebSocket 接口
WS     /ws/sessions/{id}/logs           # 实时日志推送
```

#### 4. Dashboard API (`backend/app/api/dashboard.py`)

```python
GET    /api/dashboard/stats             # 总览统计（总会话数、总 token、活跃会话）
GET    /api/dashboard/usage-by-instance # 按实例分组的 token 用量
```

#### 5. Instance 服务层 (`backend/app/services/instance_service.py`)

负责实例的业务逻辑：
- 输入验证（endpoint 和 API key 非空、名称唯一性校验）
- API key 脱敏处理（仅展示最后 4 位）
- 检查实例是否有活跃会话

```python
class InstanceService:
    async def create_instance(self, data: InstanceCreate) -> Instance
    async def list_instances(self) -> list[InstanceSummary]
    async def get_instance(self, id: str) -> Instance
    async def update_instance(self, id: str, data: InstanceUpdate) -> Instance
    async def delete_instance(self, id: str) -> None  # raises if active session
    
    @staticmethod
    def mask_api_key(api_key: str) -> str:
        """将 API key 脱敏，仅保留最后 4 位"""
        if len(api_key) <= 4:
            return "****"
        return "*" * (len(api_key) - 4) + api_key[-4:]
```

#### 6. Session 服务层 (`backend/app/services/session_service.py`)

负责会话生命周期管理：
- 创建 LiveKit 房间和 Token
- 启动 Agent Worker 子进程
- 终止会话和清理资源
- Token 用量聚合查询

```python
class SessionService:
    async def create_session(self, instance_id: str) -> SessionResponse
    async def stop_session(self, session_id: str) -> None
    async def get_session(self, session_id: str) -> SessionDetail
    async def list_sessions(self, page: int, page_size: int, instance_id: str | None) -> PaginatedSessions
    async def delete_session(self, session_id: str) -> None
    async def report_token_usage(self, session_id: str, input_tokens: int, output_tokens: int) -> None
    async def get_instance_token_totals(self, instance_id: str) -> TokenSummary
```

#### 7. Agent Worker (`backend/app/agent_worker.py`)

独立的 Python 脚本，作为子进程运行：
- 通过环境变量接收 Instance 凭据和 LiveKit 房间信息
- 使用 `livekit-agents` + `livekit-plugins-openai` 连接 Azure OpenAI Realtime
- 通过 stdout JSON lines 输出日志事件
- 会话结束时通过 HTTP 上报 Token 用量

```python
# 启动参数（通过环境变量传入）
AZURE_ENDPOINT=...
AZURE_API_KEY=...
AZURE_DEPLOYMENT=...
LIVEKIT_URL=...
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
ROOM_NAME=...
SESSION_ID=...
REPORT_URL=http://localhost:8090/internal/sessions/{session_id}/usage
```

#### 8. Process Manager (`backend/app/services/process_manager.py`)

管理 Agent Worker 子进程的生命周期：

```python
class ProcessManager:
    async def spawn_agent(self, session_id: str, instance: Instance, room_name: str) -> None
    async def terminate_agent(self, session_id: str) -> None
    async def is_agent_running(self, session_id: str) -> bool
    def get_active_sessions(self) -> list[str]
```

#### 9. Log Broadcaster (`backend/app/services/log_broadcaster.py`)

管理调试日志的收集和广播：
- 从 Agent Worker stdout 读取 JSON lines 日志
- 通过 WebSocket 广播给订阅的前端客户端
- 会话结束后批量写入 SQLite

```python
class LogBroadcaster:
    async def subscribe(self, session_id: str, websocket: WebSocket) -> None
    async def unsubscribe(self, session_id: str, websocket: WebSocket) -> None
    async def broadcast(self, session_id: str, log_entry: LogEntry) -> None
    async def persist_logs(self, session_id: str) -> None
```

### 前端组件

#### 页面路由

| 路径 | 页面 | 说明 |
|------|------|------|
| `/` | Dashboard | 总览统计、快速操作入口 |
| `/instances` | Instance List | 实例 CRUD 列表 |
| `/instances/:id` | Instance Detail | 实例详情 + 该实例的历史用量 |
| `/sessions/new?instance=:id` | Voice Session | 语音对话 + 调试控制台 |
| `/history` | Session History | 历史会话列表 |
| `/history/:id` | Session Detail | 会话详情 + 日志回放 |

#### 核心前端组件

```
components/
├── layout/
│   ├── AppShell.tsx          # 主布局（侧边栏 + 内容区）
│   └── Sidebar.tsx           # 导航侧边栏
├── instances/
│   ├── InstanceForm.tsx      # 创建/编辑实例表单
│   ├── InstanceCard.tsx      # 实例卡片展示
│   └── InstanceList.tsx      # 实例列表
├── session/
│   ├── VoiceRoom.tsx         # 语音房间（LiveKit 集成）
│   ├── DebugConsole.tsx      # 调试日志面板
│   ├── LogEntry.tsx          # 单条日志展示
│   ├── LogFilter.tsx         # 日志过滤器
│   └── ConnectionStatus.tsx  # 连接状态指示
├── history/
│   ├── SessionList.tsx       # 历史会话列表
│   ├── SessionRow.tsx        # 会话摘要行
│   └── SessionDetail.tsx     # 会话详情
└── dashboard/
    ├── StatsCard.tsx         # 统计卡片
    └── UsageChart.tsx        # 用量图表
```

#### 自定义 Hooks

```typescript
// hooks/useLiveKit.ts - LiveKit 房间连接管理
function useLiveKit(token: string, url: string): {
  room: Room | null;
  connectionState: ConnectionState;
  connect: () => Promise<void>;
  disconnect: () => void;
}

// hooks/useSessionLogs.ts - WebSocket 实时日志
function useSessionLogs(sessionId: string): {
  logs: LogEntry[];
  isConnected: boolean;
  filter: (eventType: string) => void;
}

// hooks/useApi.ts - REST API 封装
function useApi<T>(url: string, options?: RequestInit): {
  data: T | null;
  error: Error | null;
  loading: boolean;
  refetch: () => void;
}
```

## Data Models

### 数据库 Schema (SQLite)

```sql
-- 实例配置表
CREATE TABLE instances (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    api_key TEXT NOT NULL,
    deployment TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 会话记录表
CREATE TABLE sessions (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    instance_id TEXT NOT NULL REFERENCES instances(id),
    room_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'connecting',  -- connecting, connected, completed, error, cancelled
    start_time TEXT NOT NULL DEFAULT (datetime('now')),
    end_time TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    error_message TEXT
);

-- 会话日志表
CREATE TABLE session_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    timestamp TEXT NOT NULL,
    direction TEXT NOT NULL,  -- inbound, outbound, internal
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_sessions_instance_id ON sessions(instance_id);
CREATE INDEX idx_sessions_start_time ON sessions(start_time DESC);
CREATE INDEX idx_session_logs_session_id ON session_logs(session_id);
CREATE INDEX idx_session_logs_event_type ON session_logs(event_type);
```

### Pydantic Models (Backend)

```python
# 请求/响应模型
class InstanceCreate(BaseModel):
    name: str                    # 非空，唯一
    endpoint: str                # 非空，Azure 端点 URL
    api_key: str                 # 非空
    deployment: str              # 非空，部署名称
    description: str = ""

class InstanceUpdate(BaseModel):
    name: str | None = None
    endpoint: str | None = None
    api_key: str | None = None
    deployment: str | None = None
    description: str | None = None

class InstanceSummary(BaseModel):
    id: str
    name: str
    endpoint: str
    deployment: str
    description: str
    created_at: str
    # 注意：不包含 api_key

class InstanceDetail(BaseModel):
    id: str
    name: str
    endpoint: str
    api_key_masked: str          # 脱敏后的 key
    deployment: str
    description: str
    created_at: str
    updated_at: str
    total_sessions: int
    total_input_tokens: int
    total_output_tokens: int

class SessionCreate(BaseModel):
    instance_id: str

class SessionResponse(BaseModel):
    session_id: str
    room_name: str
    livekit_token: str           # 用户加入房间的 token
    livekit_url: str

class SessionDetail(BaseModel):
    id: str
    instance_id: str
    instance_name: str
    room_name: str
    status: str
    start_time: str
    end_time: str | None
    input_tokens: int
    output_tokens: int
    error_message: str | None

class LogEntry(BaseModel):
    id: int
    session_id: str
    timestamp: str
    direction: str               # inbound | outbound | internal
    event_type: str
    payload: str                 # JSON string

class PaginatedSessions(BaseModel):
    items: list[SessionDetail]
    total: int
    page: int
    page_size: int

class TokenUsageReport(BaseModel):
    input_tokens: int
    output_tokens: int

class DashboardStats(BaseModel):
    total_instances: int
    total_sessions: int
    active_sessions: int
    total_input_tokens: int
    total_output_tokens: int

class InstanceUsage(BaseModel):
    instance_id: str
    instance_name: str
    session_count: int
    total_input_tokens: int
    total_output_tokens: int
```

### TypeScript Types (Frontend)

```typescript
interface Instance {
  id: string;
  name: string;
  endpoint: string;
  deployment: string;
  description: string;
  created_at: string;
}

interface InstanceDetail extends Instance {
  api_key_masked: string;
  updated_at: string;
  total_sessions: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

interface Session {
  id: string;
  instance_id: string;
  instance_name: string;
  room_name: string;
  status: 'connecting' | 'connected' | 'completed' | 'error' | 'cancelled';
  start_time: string;
  end_time: string | null;
  input_tokens: number;
  output_tokens: number;
  error_message: string | null;
}

interface LogEntry {
  id: number;
  session_id: string;
  timestamp: string;
  direction: 'inbound' | 'outbound' | 'internal';
  event_type: string;
  payload: string;
}

type ConnectionState = 'idle' | 'connecting' | 'connected' | 'agent_speaking' | 'user_speaking' | 'disconnected';
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Instance 输入验证拒绝无效凭据

*For any* string that is empty or composed entirely of whitespace characters, submitting it as the endpoint or API key field of an Instance creation request SHALL result in a validation error, and the Instance SHALL NOT be persisted.

**Validates: Requirements 1.5**

### Property 2: API Key 脱敏保留末尾字符

*For any* API key string of length >= 4, the mask function SHALL return a string of the same length where the last 4 characters match the original and all preceding characters are replaced with `*`. For any API key of length < 4, the mask function SHALL return `****`.

**Validates: Requirements 1.6**

### Property 3: Instance 名称唯一性

*For any* Instance name that already exists in the Instance_Store, attempting to create a new Instance with the same name SHALL be rejected with a uniqueness error.

**Validates: Requirements 1.7**

### Property 4: Token 事件聚合一致性

*For any* sequence of token usage report events associated with a session, the total input_tokens and output_tokens persisted for that session SHALL equal the sum of all individual report events' input_tokens and output_tokens respectively.

**Validates: Requirements 3.2**

### Property 5: 按实例聚合 Token 用量正确性

*For any* set of sessions in the Session_Store, the cumulative token usage reported for an Instance SHALL equal the sum of input_tokens and output_tokens of all sessions belonging to that Instance.

**Validates: Requirements 3.3, 3.5**

### Property 6: 日志条目结构完整性

*For any* WebSocket event captured by the Debug_Logger, the resulting LogEntry SHALL contain non-empty values for: event_type, timestamp, direction (one of inbound/outbound/internal), and payload.

**Validates: Requirements 4.3**

### Property 7: 日志按事件类型过滤正确性

*For any* set of LogEntry records and any selected event_type filter value, the filtered result SHALL contain exactly those entries whose event_type matches the filter value, and no entries with a different event_type.

**Validates: Requirements 4.7**

### Property 8: 会话历史按时间降序排列

*For any* paginated query result of sessions, each session's start_time SHALL be greater than or equal to the start_time of the subsequent session in the list (most recent first).

**Validates: Requirements 5.1**

### Property 9: 会话元数据完整性

*For any* completed Voice_Session, the Session_Store record SHALL contain non-null values for: session_id, instance_id, room_name, start_time, end_time, status, input_tokens, and output_tokens.

**Validates: Requirements 5.2**

### Property 10: 会话历史按实例过滤正确性

*For any* set of sessions and a selected Instance name filter, the filtered result SHALL contain only sessions whose associated Instance name matches the filter, and all matching sessions SHALL be included.

**Validates: Requirements 5.5**

## Error Handling

### 错误分类与策略

| 错误类型 | 场景 | 处理策略 |
|---------|------|---------|
| 输入验证错误 | Instance 字段为空/重名 | 返回 422 + 具体字段错误信息 |
| 资源不存在 | 查询不存在的 Instance/Session | 返回 404 |
| 业务约束冲突 | 删除有活跃会话的 Instance | 返回 409 + 冲突说明 |
| LiveKit 连接失败 | 启动时 LiveKit 不可达 | 日志警告，降级运行（禁用会话创建）|
| Agent Worker 启动失败 | 子进程 spawn 出错 | 标记 session 为 error，返回错误给前端 |
| Azure API 认证失败 | Instance 凭据无效 | Agent 上报错误，session 标记 error |
| WebSocket 断连 | 网络中断 | 前端自动重连，超时后提示用户 |
| 数据库操作失败 | SQLite 写入错误 | 返回 500，日志记录详情 |

### 前端错误处理

- 所有 API 请求使用统一的错误拦截器，自动展示 toast 通知
- WebSocket 断连后自动重连（最多 3 次，间隔递增）
- LiveKit 连接状态变更实时反映在 UI 上
- 表单验证错误内联显示在对应字段下方

### Agent Worker 错误上报

Agent Worker 通过 stdout JSON lines 上报错误事件：

```json
{"type": "error", "timestamp": "...", "message": "Azure API auth failed", "details": "..."}
```

FastAPI 收到错误后：
1. 更新 session 状态为 `error`
2. 记录 error_message
3. 通过 WebSocket 推送给前端
4. 终止 Agent Worker 进程

## Testing Strategy

### 测试分层

```
┌───────────────────────────┐
│   E2E Tests (少量)         │  Playwright - 关键用户流程
├───────────────────────────┤
│   Integration Tests        │  pytest + httpx - API 端到端
├───────────────────────────┤
│   Property Tests           │  Hypothesis (Python) - 正确性属性
├───────────────────────────┤
│   Unit Tests               │  pytest + vitest - 纯逻辑
└───────────────────────────┘
```

### 属性测试 (Property-Based Testing)

使用 Python **Hypothesis** 库实现属性测试，每个属性至少运行 100 次迭代。

适用范围：
- 输入验证逻辑（Property 1, 3）
- API key 脱敏函数（Property 2）
- Token 聚合计算（Property 4, 5）
- 日志结构验证（Property 6）
- 过滤和排序逻辑（Property 7, 8, 10）
- 数据完整性约束（Property 9）

每个属性测试需要标注对应的设计属性编号：
```python
# Feature: azure-voice-testing-admin, Property 2: API Key 脱敏保留末尾字符
@given(api_key=st.text(min_size=1, max_size=100))
def test_mask_api_key_preserves_last_four(api_key):
    ...
```

### 单元测试

使用 **pytest** (后端) 和 **vitest** (前端) 实现：

后端重点：
- Service 层的边界条件（空列表、单条记录）
- 数据库 CRUD 的具体场景
- Agent Worker spawn 参数构造

前端重点：
- 组件渲染（React Testing Library）
- Hook 行为（act + 模拟 WebSocket）
- 路由跳转逻辑

### 集成测试

使用 **pytest + httpx.AsyncClient** 测试 FastAPI 端点：
- 完整的 CRUD 流程
- WebSocket 连接和消息收发
- 错误响应格式验证
- 数据库状态验证

### 测试工具配置

| 工具 | 用途 | 配置 |
|------|------|------|
| pytest | 后端测试运行 | pytest.ini / pyproject.toml |
| hypothesis | 属性测试 | settings(max_examples=100) |
| vitest | 前端单元测试 | vitest.config.ts |
| httpx | API 集成测试 | AsyncClient + TestClient |
| React Testing Library | 组件测试 | @testing-library/react |
