# Implementation Plan: Azure Realtime Voice Testing Management System

## Overview

基于 FastAPI + React + SQLite + LiveKit 实现本地部署的 Azure OpenAI Realtime 语音测试管理面板。所有代码实现在 `azure-voice-admin/` 子目录下，后端位于 `azure-voice-admin/backend/`，前端位于 `azure-voice-admin/frontend/`。

## Tasks

- [x] 1. Phase 1: 项目脚手架与后端基础
  - [x] 1.1 初始化后端项目结构 (FastAPI + 依赖)
    - 创建 `azure-voice-admin/backend/` 目录结构：`app/`, `app/api/`, `app/services/`, `app/models/`, `tests/`
    - 创建 `pyproject.toml`，声明依赖：fastapi, uvicorn, aiosqlite, livekit-api, pydantic, hypothesis, pytest, httpx
    - 创建 `app/__init__.py`, `app/main.py`（FastAPI 实例 + CORS 中间件 + 静态文件 mount）
    - 创建 `.env.example` 文件定义环境变量模板（LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, DB_PATH, PORT）
    - _Requirements: 6.1, 6.2_

  - [x] 1.2 初始化前端项目结构 (React + Vite + Tailwind + shadcn/ui)
    - 使用 Vite 创建 `azure-voice-admin/frontend/` React + TypeScript 项目
    - 配置 Tailwind CSS 和 shadcn/ui
    - 创建基本目录结构：`src/components/`, `src/pages/`, `src/hooks/`, `src/lib/`, `src/types/`
    - 添加依赖：react-router-dom, @livekit/components-react, livekit-client, lucide-react, recharts
    - 创建 `src/types/index.ts` 定义所有 TypeScript 类型（Instance, Session, LogEntry, ConnectionState 等）
    - _Requirements: 1.2, 2.3_

  - [x] 1.3 创建 SQLite 数据库 Schema 和初始化
    - 创建 `app/database.py`：数据库连接管理（aiosqlite），提供 `get_db()` 依赖注入
    - 创建 `app/schema.sql`：instances / sessions / session_logs 三张表及索引
    - 在 `app/database.py` 中实现 `init_db()` 函数，启动时自动执行 schema 初始化
    - _Requirements: 6.5_

  - [x] 1.4 创建 Pydantic 数据模型
    - 创建 `app/models/instance.py`：InstanceCreate, InstanceUpdate, InstanceSummary, InstanceDetail
    - 创建 `app/models/session.py`：SessionCreate, SessionResponse, SessionDetail, PaginatedSessions, TokenUsageReport
    - 创建 `app/models/log.py`：LogEntry
    - 创建 `app/models/dashboard.py`：DashboardStats, InstanceUsage
    - 所有模型严格按照 design.md 中的定义实现
    - _Requirements: 1.1, 2.1, 3.1, 5.2_

- [x] 2. Phase 2: 实例管理 (后端 + 前端)
  - [x] 2.1 实现后端 Instance 服务层
    - 创建 `app/services/instance_service.py`，实现 InstanceService 类
    - 实现 `create_instance()`：验证非空、唯一性校验、写入 SQLite
    - 实现 `list_instances()`：查询所有实例，返回 InstanceSummary（不含 API key）
    - 实现 `get_instance()`：返回 InstanceDetail，包含脱敏 API key 和 token 统计
    - 实现 `update_instance()`：部分更新
    - 实现 `delete_instance()`：检查是否有活跃会话，有则拒绝删除
    - 实现 `mask_api_key()` 静态方法：长度 >= 4 时保留末尾 4 位替换其余为 `*`，否则返回 `****`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 2.2 实现后端 Instance REST API
    - 创建 `app/api/instances.py`，注册路由到 FastAPI app
    - 实现 `GET /api/instances`：调用 service 层返回列表
    - 实现 `POST /api/instances`：创建实例，验证失败返回 422
    - 实现 `GET /api/instances/{id}`：获取详情
    - 实现 `PUT /api/instances/{id}`：更新实例
    - 实现 `DELETE /api/instances/{id}`：删除实例，有活跃会话返回 409
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 2.3 编写 Instance 服务层属性测试
    - **Property 1: Instance 输入验证拒绝无效凭据**
    - **Property 2: API Key 脱敏保留末尾字符**
    - **Property 3: Instance 名称唯一性**
    - 使用 Hypothesis 为 mask_api_key、输入验证、名称唯一性编写属性测试
    - **Validates: Requirements 1.5, 1.6, 1.7**

  - [x] 2.4 实现前端 Instance 列表页面
    - 创建 `src/pages/InstancesPage.tsx`：展示所有实例卡片列表
    - 创建 `src/components/instances/InstanceCard.tsx`：展示名称、endpoint、deployment、创建时间
    - 创建 `src/components/instances/InstanceList.tsx`：列表容器 + 空状态
    - 实现 API 调用 hook `src/hooks/useApi.ts`
    - 添加"新建实例"按钮入口
    - _Requirements: 1.2_

  - [x] 2.5 实现前端 Instance 创建/编辑表单
    - 创建 `src/components/instances/InstanceForm.tsx`：表单组件（name, endpoint, api_key, deployment, description）
    - 实现前端字段验证（endpoint 和 api_key 非空）
    - 创建/编辑模式复用同一组件
    - 提交成功后导航回列表页
    - _Requirements: 1.1, 1.3, 1.5_

- [x] 3. Phase 3: 会话管理与 Agent Worker
  - [x] 3.1 实现后端 Session REST API
    - 创建 `app/api/sessions.py`，注册路由
    - 实现 `POST /api/sessions`：创建会话（生成房间名、Token、启动 Agent）
    - 实现 `POST /api/sessions/{id}/stop`：终止会话
    - 实现 `GET /api/sessions`：会话历史列表（支持分页 page/page_size、按 instance_id 筛选）
    - 实现 `GET /api/sessions/{id}`：会话详情
    - 实现 `DELETE /api/sessions/{id}`：删除会话记录及其日志
    - 实现内部端点 `POST /internal/sessions/{id}/usage`：Agent Worker Token 上报
    - _Requirements: 2.1, 2.4, 5.1, 5.3, 5.4, 3.2_

  - [x] 3.2 实现 Session 服务层
    - 创建 `app/services/session_service.py`，实现 SessionService 类
    - `create_session()`：验证 instance 存在 → 生成 room_name → 调用 LiveKit API 创建房间和 Token → 写入 sessions 表 → 调用 ProcessManager spawn agent
    - `stop_session()`：调用 ProcessManager terminate → 更新 session 状态为 completed/cancelled → 记录 end_time
    - `report_token_usage()`：累加 input_tokens / output_tokens 到 sessions 表
    - `list_sessions()` / `get_session()` / `delete_session()`
    - _Requirements: 2.1, 2.4, 3.2, 5.1, 5.2, 5.4_

  - [x] 3.3 实现 Agent Worker 脚本
    - 创建 `app/agent_worker.py`：独立可执行的 Python 脚本
    - 从环境变量读取 Azure 凭据和 LiveKit 房间信息
    - 使用 `livekit-agents` + `openai` realtime plugin 连接 Azure OpenAI Realtime API
    - 通过 stdout JSON lines 输出事件日志（event_type, timestamp, direction, payload）
    - 解析 `response.done` 事件中的 usage 字段，会话结束时 HTTP POST 上报 Token 用量到 `/internal/sessions/{id}/usage`
    - 出错时输出 `{"type": "error", ...}` 格式的日志
    - _Requirements: 2.2, 2.7, 3.1, 4.1, 4.3_

  - [x] 3.4 实现 Process Manager
    - 创建 `app/services/process_manager.py`，实现 ProcessManager 类
    - `spawn_agent()`：使用 `asyncio.create_subprocess_exec` 启动 agent_worker.py 子进程，传入环境变量
    - `terminate_agent()`：发送 SIGTERM 终止子进程，超时后 SIGKILL
    - `is_agent_running()` / `get_active_sessions()`：查询子进程状态
    - 维护 `dict[str, asyncio.subprocess.Process]` 映射 session_id → process
    - _Requirements: 2.4, 2.6, 6.6_

  - [ ]* 3.5 编写 Token 聚合属性测试
    - **Property 4: Token 事件聚合一致性**
    - **Property 5: 按实例聚合 Token 用量正确性**
    - 使用 Hypothesis 生成随机 token usage 事件序列，验证聚合逻辑
    - **Validates: Requirements 3.2, 3.3, 3.5**

- [x] 4. Phase 4: 调试控制台与实时日志
  - [x] 4.1 实现后端 Log Broadcaster
    - 创建 `app/services/log_broadcaster.py`，实现 LogBroadcaster 类
    - `subscribe()` / `unsubscribe()`：管理 WebSocket 客户端订阅
    - `broadcast()`：向所有订阅该 session 的客户端推送日志
    - 从 Agent Worker stdout 异步读取 JSON lines，解析为 LogEntry 后 broadcast
    - `persist_logs()`：会话结束后批量写入 session_logs 表
    - 集成到 ProcessManager 的 spawn 流程中（spawn 后启动 stdout reader 协程）
    - _Requirements: 4.1, 4.2, 4.6_

  - [x] 4.2 实现后端 WebSocket 日志端点
    - 在 `app/api/sessions.py` 中添加 `WS /ws/sessions/{id}/logs` 端点
    - 连接时调用 LogBroadcaster.subscribe，断开时 unsubscribe
    - 支持向客户端推送 LogEntry JSON 消息
    - _Requirements: 4.2_

  - [x] 4.3 实现前端 Debug Console 组件
    - 创建 `src/components/session/DebugConsole.tsx`：日志面板主容器
    - 创建 `src/components/session/LogEntry.tsx`：单条日志展示（时间戳、方向图标、event_type、payload 摘要）
    - 创建 `src/components/session/LogFilter.tsx`：event_type 下拉过滤器
    - 创建 `src/hooks/useSessionLogs.ts`：WebSocket 连接管理 + 日志状态 + 过滤逻辑
    - 点击日志条目展开完整 payload（格式化 JSON 展示）
    - 错误日志高亮显示（红色背景/边框）
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.7_

  - [ ]* 4.4 编写日志结构和过滤属性测试
    - **Property 6: 日志条目结构完整性**
    - **Property 7: 日志按事件类型过滤正确性**
    - 使用 Hypothesis 生成随机 LogEntry 数据，验证结构和过滤逻辑
    - **Validates: Requirements 4.3, 4.7**

- [x] 5. Checkpoint - 核心功能验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Phase 5: Dashboard 与会话历史
  - [x] 6.1 实现后端 Dashboard API
    - 创建 `app/api/dashboard.py`，注册路由
    - 实现 `GET /api/dashboard/stats`：查询总实例数、总会话数、活跃会话数、总 token 用量
    - 实现 `GET /api/dashboard/usage-by-instance`：按实例分组查询 token 用量
    - _Requirements: 3.3, 3.5_

  - [x] 6.2 实现前端 Dashboard 页面
    - 创建 `src/pages/DashboardPage.tsx`：统计卡片 + 用量图表
    - 创建 `src/components/dashboard/StatsCard.tsx`：统计数值展示卡片
    - 创建 `src/components/dashboard/UsageChart.tsx`：使用 recharts 绘制按实例的 token 用量条形图
    - _Requirements: 3.3_

  - [x] 6.3 实现前端 Session History 页面
    - 创建 `src/pages/HistoryPage.tsx`：会话历史列表（分页 + 按实例筛选）
    - 创建 `src/components/history/SessionList.tsx`：列表容器
    - 创建 `src/components/history/SessionRow.tsx`：单行摘要（Instance 名称、开始时间、时长、token 数量、状态标识）
    - 创建 `src/pages/SessionDetailPage.tsx`：会话详情页（元数据 + 保存的调试日志回放）
    - _Requirements: 5.1, 5.3, 5.5, 5.6_

  - [ ]* 6.4 编写会话历史排序和过滤属性测试
    - **Property 8: 会话历史按时间降序排列**
    - **Property 9: 会话元数据完整性**
    - **Property 10: 会话历史按实例过滤正确性**
    - 使用 Hypothesis 生成随机会话数据，验证排序和过滤逻辑
    - **Validates: Requirements 5.1, 5.2, 5.5**

- [x] 7. Phase 6: 集成与系统打磨
  - [x] 7.1 实现前端 Voice Session 页面
    - 创建 `src/pages/VoiceSessionPage.tsx`：左侧语音房间 + 右侧调试控制台
    - 创建 `src/components/session/VoiceRoom.tsx`：集成 @livekit/components-react，提供连接/断开控制
    - 创建 `src/components/session/ConnectionStatus.tsx`：实时展示连接状态（connecting → connected → speaking 等）
    - 创建 `src/hooks/useLiveKit.ts`：管理 LiveKit Room 连接生命周期
    - "Start Session" 按钮触发 POST /api/sessions → 获取 token → 连接房间
    - "End Session" 按钮触发 POST /api/sessions/{id}/stop → 断开房间
    - _Requirements: 2.1, 2.3, 2.4, 2.7_

  - [x] 7.2 实现前端布局（AppShell + Sidebar + 路由）
    - 创建 `src/components/layout/AppShell.tsx`：主布局结构（左侧导航 + 右侧内容）
    - 创建 `src/components/layout/Sidebar.tsx`：导航菜单（Dashboard, Instances, History）
    - 配置 react-router-dom 路由：`/`, `/instances`, `/instances/:id`, `/sessions/new`, `/history`, `/history/:id`
    - 在 `src/App.tsx` 中整合路由和布局
    - _Requirements: 1.2, 5.1_

  - [x] 7.3 实现系统启动脚本
    - 创建 `azure-voice-admin/start.py`：单命令启动入口
    - 启动流程：初始化数据库 → 检查 LiveKit 连通性（不可达则警告并降级）→ 启动 uvicorn 服务
    - 支持通过环境变量或 `.env` 文件配置端口、LiveKit 地址等
    - 在 `app/main.py` 的 lifespan 事件中集成 init_db + LiveKit 健康检查
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 7.4 配置生产构建（前端静态文件由 FastAPI 托管）
    - 在 `frontend/package.json` 中配置 `build` 脚本，输出到 `../backend/static/`
    - 在 FastAPI `app/main.py` 中使用 `StaticFiles` mount `/` 路径服务前端构建产物
    - 配置 SPA fallback（所有非 `/api/` 和 `/ws/` 路径返回 index.html）
    - 更新 `start.py` 添加可选的前端构建步骤
    - _Requirements: 6.2_

- [x] 8. Final Checkpoint - 全功能验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 后端使用 Python (FastAPI + aiosqlite + Hypothesis)，前端使用 TypeScript (React + Vite + Tailwind + shadcn/ui)
- 每个属性测试最少运行 100 次迭代
- Property tests validate universal correctness properties; unit tests validate specific examples and edge cases
- Agent Worker 作为独立子进程运行，通过 stdout JSON lines 和 HTTP 回调与主进程通信
- 所有 API key 在传输和展示中均需脱敏处理

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4"] },
    { "id": 2, "tasks": ["2.1", "2.4"] },
    { "id": 3, "tasks": ["2.2", "2.5"] },
    { "id": 4, "tasks": ["2.3", "3.1", "3.3"] },
    { "id": 5, "tasks": ["3.2", "3.4"] },
    { "id": 6, "tasks": ["3.5", "4.1"] },
    { "id": 7, "tasks": ["4.2", "4.3"] },
    { "id": 8, "tasks": ["4.4", "6.1"] },
    { "id": 9, "tasks": ["6.2", "6.3"] },
    { "id": 10, "tasks": ["6.4", "7.1", "7.2"] },
    { "id": 11, "tasks": ["7.3", "7.4"] }
  ]
}
```
