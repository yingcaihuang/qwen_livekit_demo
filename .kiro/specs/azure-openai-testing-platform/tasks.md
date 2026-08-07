# Implementation Plan: Azure OpenAI Testing Platform

## Overview

在现有 **Azure Realtime Voice Testing Management System**（`azure-voice-admin/`）基础上，按「扩展而非重写」原则升级为支持 `voice` / `chat` / `image` 三种测试类型的通用测试平台。后端位于 `azure-voice-admin/backend/`（FastAPI + aiosqlite/SQLite），前端位于 `azure-voice-admin/frontend/`（React 19 + Vite + Tailwind v4）。任务按「后端先于前端」的数据依赖顺序推进：先完成 Schema 迁移与配置，再实现实例类型、Chat、Image 后端与统一历史/仪表盘，最后落地前端页面，并以构建与测试验证收尾。所有 Azure 调用与文件落盘在测试中均使用 mock / tmp 目录。

## Tasks

- [x] 1. Phase 1: 数据库 Schema 与幂等向后兼容迁移
  - [x] 1.1 扩展 Schema 定义（instances.type + image_generations 表）
    - 在 `app/schema.sql` 的 `instances` 建表语句中新增 `type TEXT NOT NULL DEFAULT 'voice'` 列（fresh DB 路径）
    - 新增 `image_generations` 表（`CREATE TABLE IF NOT EXISTS`）及其字段：`id, instance_id, session_id, prompt, params, size, quality, output_format, compression, n, has_reference, input_tokens, output_tokens, image_paths, status, error_message, created_at`
    - 新增索引 `idx_image_generations_instance_id`、`idx_image_generations_created_at`（均 `IF NOT EXISTS`）
    - _Requirements: 8.1, 8.3, 9.5, 5.2_

  - [x] 1.2 实现启动时幂等迁移逻辑
    - 在 `app/database.py` 新增 `_migrate(db)`：用 `PRAGMA table_info(instances)` 检查 `type` 列是否存在，不存在则 `ALTER TABLE instances ADD COLUMN type TEXT NOT NULL DEFAULT 'voice'`（既有行回填为 `voice`）
    - 在 `init_db()` 中于执行 `schema.sql` 后调用 `_migrate`；捕获异常时记录详细日志并向上抛出以中止启动（避免半迁移状态）
    - 确保重复启动幂等（列已存在则跳过 ALTER；表用 IF NOT EXISTS）
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 6.6_

  - [x]* 1.3 编写迁移幂等性属性/集成测试
    - **Property 16: 迁移幂等且默认归类为 voice**
    - 以「旧版本 schema（无 type、无 image_generations）」建临时库，多次运行 `init_db` 后断言：`type` 列存在、既有行 `type='voice'`、既有数据不丢失、重复运行不报错
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 6.6**

- [x] 2. Phase 2: 配置模块
  - [x] 2.1 新增 Azure OpenAI 配置模块
    - 创建 `app/config.py`：读取 `AZURE_OPENAI_CHAT_API_VERSION`、`AZURE_OPENAI_IMAGE_API_VERSION`（均有默认值）、`DATA_DIR`、`IMAGES_DIR_NAME`、`MAX_REFERENCE_IMAGE_BYTES`
    - 在 `.env.example` 中补充上述新环境变量模板
    - _Requirements: 9.4, 9.5_

- [x] 3. Phase 3: 实例类型管理（后端）
  - [x] 3.1 扩展 Instance Pydantic 模型
    - 在 `app/models/instance.py` 定义 `InstanceType = Literal["voice","chat","image"]`
    - `InstanceCreate` 新增必填 `type: InstanceType`；`InstanceUpdate` 不含 `type` 字段（创建后不可变）
    - `InstanceSummary` / `InstanceDetail` 新增 `type` 字段
    - _Requirements: 1.1, 1.2, 1.7_

  - [x] 3.2 扩展 Instance 服务层
    - 在 `app/services/instance_service.py` 的 `create_instance()` 中校验 `type` 属于 {voice, chat, image}，非法/缺失则拒绝
    - `list_instances()` 支持按 `type` 筛选参数
    - `update_instance()` 忽略/拒绝任何 `type` 变更，保证类型不可变
    - 更新时若未提供新 api_key，保留并返回既有脱敏 key（不覆盖为空）
    - _Requirements: 1.1, 1.2, 1.7, 1.8, 9.3_

  - [x] 3.3 扩展 Instance REST API
    - `GET /api/instances?type=voice|chat|image`：透传类型筛选到 service 层
    - `POST /api/instances`：`type` 缺失/非法返回 422
    - `PUT /api/instances/{id}`：请求体不含 `type`，忽略类型变更
    - `GET /api/instances/{id}`：响应含 `type` 与脱敏 key
    - _Requirements: 1.1, 1.2, 1.7, 1.8_

  - [x]* 3.4 编写实例类型属性测试
    - **Property 1: 实例类型往返一致性 (Validates: Requirements 1.1)**
    - **Property 2: 非法或缺失类型被拒绝 (Validates: Requirements 1.2)**
    - **Property 3: 实例类型创建后不可变 (Validates: Requirements 1.7)**
    - **Property 4: 按类型筛选正确性 (Validates: Requirements 1.8, 6.3, 7.2)**
    - **Property 17: API Key 脱敏保留末尾字符 (Validates: Requirements 9.3)**

  - [x]* 3.5 编写 Instance API 集成测试
    - 覆盖创建携带合法/非法 type、按 type 筛选列表、编辑不改变 type、脱敏 key 保留
    - _Requirements: 1.1, 1.2, 1.7, 1.8, 9.3_

- [x] 4. Phase 4: Chat 对话后端
  - [x] 4.1 新增 Chat Pydantic 模型
    - 在 `app/models/chat.py` 定义 `ChatMessage`、`ChatCompletionRequest`（instance_id/session_id/messages/system_prompt/temperature/max_tokens）、`ChatMessageRecord`
    - _Requirements: 2.1, 2.3, 2.4, 3.2_

  - [x] 4.2 实现 Chat 服务层（流式代理 + 参数约束 + 用量累加）
    - 创建 `app/services/chat_service.py`，实现 `ChatService`
    - `_clamp_temperature()` 约束到 [0,2]；`_sanitize_max_tokens()` None 透传否则正整数；`_azure_chat_url()` 拼接部署 URL + `AZURE_OPENAI_CHAT_API_VERSION`
    - `stream_chat()`：用 `aiohttp` 以 `stream=true` + `stream_options.include_usage` 调用 Azure Chat Completions，逐块解析 `data:` 行累积 `delta.content`，末尾读取 usage（缺失记为 0），逐行 yield SSE 文本；`system_prompt` 注入首条 system 消息
    - `new_conversation()`：创建 `status='active'` 的 chat 会话记录并返回 session_id
    - 日志与响应一律脱敏 api-key
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.3, 3.6, 9.2, 9.3, 9.4_

  - [x] 4.3 实现 Chat SSE 端点与会话持久化
    - 创建 `app/api/chat.py`，实现 `POST /api/chat/completions` 返回 `StreamingResponse(media_type="text/event-stream")`
    - 首条消息时惰性创建 `sessions` 记录（类型经 `instance.type` 派生，voice 专属列如 room_name 置空串）；下发 `{"type":"session"}` / `{"type":"delta"}` / `{"type":"done"}` / `{"type":"error"}`
    - 流结束后将 user/assistant 消息（role + content + timestamp）写入 `session_messages`，并累加 `input_tokens`/`output_tokens` 到 `sessions`
    - 新增 `DELETE` 会话时级联删除关联 `session_messages`（复用/扩展 session service）
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 9.2_

  - [x]* 4.4 编写 Chat 参数与持久化属性测试
    - **Property 5: temperature 参数区间约束 (Validates: Requirements 2.5)**
    - **Property 6: max_tokens 参数约束为正整数 (Validates: Requirements 2.6)**
    - **Property 8: 对话 Token 用量累加一致性 (Validates: Requirements 3.3, 3.6)**
    - **Property 9: 对话消息持久化完整性 (Validates: Requirements 3.2)**
    - **Property 10: 会话删除级联清理消息 (Validates: Requirements 3.5)**

  - [x]* 4.5 编写 Chat API 集成测试
    - mock aiohttp 流式响应，验证 `POST /api/chat/completions` 的 SSE 解析、会话惰性创建、消息与用量持久化、错误事件下发
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 3.3, 9.2, 10.3_

- [x] 5. Phase 5: Image 图像生成后端
  - [x] 5.1 新增 Image 模型与 multipart 依赖
    - 在 `app/models/image.py` 定义 `ImageParams`、`ImageGenerationRequest`、`ImageGenerationResponse`
    - 在 `pyproject.toml` 新增 `python-multipart` 依赖（FastAPI 处理 `multipart/form-data` 所需）
    - _Requirements: 4.1, 5.2_

  - [x] 5.2 实现 Image 服务层（生成/编辑 + 落盘 + 路径防护 + 清理）
    - 创建 `app/services/image_service.py`，实现 `ImageService`
    - `_clamp_compression()` 约束到 [0,100]；`_azure_*_url()` 拼接 URL + `AZURE_OPENAI_IMAGE_API_VERSION`
    - `generate()`：无参考图走 `images/generations`（JSON），有参考图走 `images/edits`（multipart）；解码每张 `b64_json` 写入 `DATA_DIR/images/<generation_id>/<index>.<ext>`；`n>1` 请求多变体
    - 「先写文件、成功后写元数据」：任一文件写入失败则清理该目录并报错，不写悬空元数据；成功后写 `image_generations`（prompt/params/usage/instance_id/image_paths）
    - `resolve_image_path()`：解析后校验绝对路径以 images 根目录为前缀，防路径穿越
    - `delete_generation()`：先删磁盘目录再删数据库行
    - _Requirements: 4.2, 4.3, 4.6, 4.7, 5.1, 5.2, 5.4, 5.5, 9.2, 9.3, 9.4, 9.5_

  - [x] 5.3 实现 Image REST API
    - 创建 `app/api/images.py`
    - `POST /api/images/generations`（`multipart/form-data`，可选 `file` 参考图）→ 调 service 返回 `{generation_id, images, usage, params}`
    - `GET /api/images/{generation_id}/{index}`：经 `resolve_image_path` 提供图片文件，越界返回 400/404
    - `DELETE /api/images/{generation_id}`：删除元数据 + 磁盘文件
    - `GET /api/images?instance_id=&page=&page_size=`（历史列表）、`GET /api/images/{generation_id}`（详情）
    - 删除实例时级联清理其名下图像目录（扩展 instance 删除流程）
    - _Requirements: 4.2, 4.3, 4.5, 5.1, 5.3, 5.4, 5.5, 9.5_

  - [x]* 5.4 编写 Image 参数与存储属性测试
    - **Property 7: compression 参数区间约束 (Validates: Requirements 4.7)**
    - **Property 11: 请求的变体数量与返回图片数量一致 (Validates: Requirements 4.6, 5.1)**
    - **Property 12: 图像元数据完整性与无悬空引用 (Validates: Requirements 5.2, 5.5)**
    - **Property 13: 图像删除清理数据库与文件 (Validates: Requirements 5.4)**
    - **Property 18: 图片文件服务的路径穿越防护 (Validates: Requirements 9.5)**

  - [x]* 5.5 编写 Image API 集成测试
    - mock Azure 响应 + `DATA_DIR` 指向 tmp，覆盖含/不含参考图两条分支、图片服务与路径穿越拒绝、`DELETE` 清理文件与元数据、落盘失败不写元数据
    - _Requirements: 4.2, 4.3, 5.1, 5.4, 5.5, 10.3_

- [x] 6. Checkpoint - 后端核心链路验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Phase 6: 统一历史 API
  - [x] 7.1 新增统一历史模型
    - 在 `app/models/history.py` 定义 `HistoryItem`（id/type/instance_id/instance_name/title/start_time/input_tokens/output_tokens/status）、`PaginatedHistory`
    - _Requirements: 6.1, 6.2, 6.5_

  - [x] 7.2 实现统一历史 API
    - 创建 `app/api/history.py`，实现 `GET /api/history?type=&instance_id=&page=&page_size=`
    - 合并 `sessions`（voice/chat，类型由 `instances.type` JOIN 派生）与 `image_generations`（image），按 start_time 倒序分页
    - 支持按 type 与 instance 筛选；title 取 chat 首条用户消息摘要 / image prompt 摘要 / voice room_name
    - 保留既有 voice 会话记录访问，不丢数据
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x]* 7.3 编写统一历史属性/集成测试
    - **Property 14: 统一历史按开始时间降序 (Validates: Requirements 6.1)**
    - **Property 4: 按类型筛选正确性 (Validates: Requirements 6.3)**
    - 混合 voice/chat/image 数据后校验排序、类型/实例筛选与分页
    - _Requirements: 6.1, 6.3, 6.4_

- [x] 8. Phase 7: 统一仪表盘聚合
  - [x] 8.1 扩展 Dashboard 模型与聚合服务
    - 在 `app/models/dashboard.py` 扩展 `DashboardStats`（total_tests = sessions + image_generations）、新增 `TypeUsage`
    - 实现跨 `sessions` 与 `image_generations` 的聚合逻辑（按 type / instance 分组），空筛选返回零值
    - _Requirements: 7.1, 7.4, 7.5_

  - [x] 8.2 扩展 Dashboard API
    - `GET /api/dashboard/stats?type=&instance_id=`：跨类型聚合总量，支持筛选
    - `GET /api/dashboard/usage-by-instance?type=`：按实例聚合（含类型分布）
    - `GET /api/dashboard/usage-by-type`：按 voice/chat/image 聚合
    - 空匹配集返回零值/空态而非报错
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x]* 8.3 编写仪表盘聚合属性测试
    - **Property 15: 仪表盘跨类型聚合正确性 (Validates: Requirements 7.1, 7.3, 7.5)**
    - **Property 4: 按类型筛选正确性 (Validates: Requirements 7.2)**

- [x] 9. Phase 8: 前端基础（类型、路由、实例表单）
  - [x] 9.1 扩展前端 TypeScript 类型
    - 在 `src/types/index.ts` 新增 `InstanceType`、扩展 `Instance.type`，新增 `ChatMessage`/`ChatParams`/`TokenUsage`、`ImageParams`/`ImageGeneration`、`HistoryItem`/`PaginatedHistory`
    - _Requirements: 1.1, 2.1, 4.1, 6.1_

  - [x] 9.2 扩展路由与实例打开逻辑
    - 在 `src/App.tsx` 新增路由：`/chat/new`、`/images/new`、`/history/image/:id`
    - `InstanceCard` 的「开始」按钮按 `instance.type` 分别跳转 `/sessions/new` / `/chat/new` / `/images/new`
    - _Requirements: 1.3, 1.4, 1.5_

  - [x] 9.3 实现实例表单类型选择器与类型徽章
    - 创建 `src/components/instances/TypeBadge.tsx`（voice/chat/image 三色渐变徽章）
    - `InstanceForm.tsx` 新增类型选择器（create 必选、edit 禁用），未选类型时前端校验报错
    - `InstanceCard.tsx` 与实例列表展示 TypeBadge，列表支持按类型筛选
    - _Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 9.1_

  - [x]* 9.4 编写前端类型/路由单元测试
    - 测试 TypeBadge 渲染、按 type 路由跳转、编辑时类型选择器禁用
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 10. Phase 9: Chat Playground 前端
  - [x] 10.1 实现 useChatStream Hook
    - 创建 `src/hooks/useChatStream.ts`：`fetch('/api/chat/completions')` + `ReadableStream` reader + `TextDecoder` 逐块解析 `data:` 行，按 `session`/`delta`/`done`/`error` 分发
    - 暴露 `messages`（含流式增量拼接的 assistant 消息）、`streaming`、`usage`、`sessionId`、`sendMessage`、`newConversation`、`error`
    - _Requirements: 2.2, 2.3, 2.7, 9.2_

  - [x] 10.2 实现 Chat Playground 页面与组件
    - 创建 `src/pages/ChatPlaygroundPage.tsx` 及 `src/components/chat/` 下 `ChatMessageList`、`ChatBubble`、`ChatComposer`、`ChatParamsPanel`
    - 逐字渲染 assistant token；参数面板含 system prompt、temperature(0-2)、max_tokens(正整数)；「新对话」清空上下文
    - 沿用彩色渐变视觉风格；流式错误内联提示且不崩溃
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 9.1, 9.2_

  - [x]* 10.3 编写 useChatStream 单元测试
    - mock `ReadableStream`，验证 SSE 分片解析与 assistant 增量拼接
    - _Requirements: 2.2, 2.3_

- [x] 11. Phase 10: Image Playground 前端
  - [x] 11.1 实现 Image Playground 页面与组件
    - 创建 `src/pages/ImagePlaygroundPage.tsx` 及 `src/components/image/` 下 `ImagePromptBar`（prompt + 内联 size/quality + 生成按钮）、`ImageParamsPanel`（compression 0-100 / format / variations 滑块 + 附参考图按钮）、`ImageResultGrid`（多变体结果网格）、`ImageEmptyState`（"Generate an image to get started"）
    - 通过 `multipart/form-data` 提交（含可选参考图）；生成失败展示错误横幅并保留参数便于重试
    - 沿用彩色渐变视觉风格
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 9.1, 9.2_

  - [x]* 11.2 编写 Image Playground 单元测试
    - 测试空态渲染、compression 滑块区间约束、多变体结果网格渲染
    - _Requirements: 4.4, 4.6, 4.7_

- [x] 12. Phase 11: 前端统一历史与仪表盘
  - [x] 12.1 实现统一历史前端（类型筛选/徽章 + 分类型详情）
    - 扩展 `src/components/history/`：`SessionList` 增加类型徽章列、`HistoryFilter` 增加类型 + 实例筛选、新增 `ImageDetail.tsx`
    - 扩展 `SessionDetailPage`：chat 展示对话转写与 token 用量；新增 `/history/image/:id` 图像详情（图片 + prompt + 参数 + usage）
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 3.4, 5.3, 9.1_

  - [x] 12.2 实现仪表盘类型筛选前端
    - 在 `DashboardPage` 复用 StatsCard/UsageChart/TokenDonutChart 等，新增类型筛选，跨类型展示聚合与按实例总量；空态展示零值
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 9.1_

- [x] 13. Final Checkpoint - 构建与测试验证
  - [x] 13.1 验证后端测试与启动
    - 运行 `pytest`（`azure-voice-admin/backend/tests/`）确保全绿；确认新增 `python-multipart` 依赖已安装
    - 确认 FastAPI 应用可导入且迁移通过（`init_db` 无误）
    - 若失败则修复后再视为完成
    - _Requirements: 10.1, 10.3, 10.4_

  - [x] 13.2 验证前端构建
    - 运行前端 `pnpm build`（Vite + TypeScript 类型检查）确保成功
    - 若失败则修复后再视为完成
    - _Requirements: 10.2, 10.4_
    - 注：Docker 镜像重建（caddy + backend + livekit）为用户手动执行步骤，不在自动化任务内

## Notes

- 标注 `*` 的子任务为可选（属性测试、单元测试、集成测试），可为快速 MVP 跳过；未标注的为核心实现任务，必须实现
- 后端使用 Python 3.12（FastAPI + aiosqlite + Hypothesis + httpx），前端使用 TypeScript（React 19 + Vite + Tailwind v4）
- 每个属性测试最少运行 100 次迭代，测试标题标注对应属性编号
- 严格「后端先于前端」：前端类型/页面依赖已完成的后端端点与响应结构
- 所有 Azure 调用在测试中以 mock 打桩，`DATA_DIR` 指向临时目录；api-key 在响应与日志中一律脱敏
- Docker 镜像重建为用户手动步骤，不作为编码任务

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "3.1"] },
    { "id": 2, "tasks": ["1.3", "3.2"] },
    { "id": 3, "tasks": ["3.3", "4.1", "5.1"] },
    { "id": 4, "tasks": ["3.4", "3.5", "4.2", "5.2"] },
    { "id": 5, "tasks": ["4.3", "5.3"] },
    { "id": 6, "tasks": ["4.4", "4.5", "5.4", "5.5", "7.1"] },
    { "id": 7, "tasks": ["7.2", "8.1"] },
    { "id": 8, "tasks": ["7.3", "8.2", "9.1"] },
    { "id": 9, "tasks": ["8.3", "9.2", "9.3"] },
    { "id": 10, "tasks": ["9.4", "10.1"] },
    { "id": 11, "tasks": ["10.2", "11.1"] },
    { "id": 12, "tasks": ["10.3", "11.2", "12.1", "12.2"] },
    { "id": 13, "tasks": ["13.1", "13.2"] }
  ]
}
```
