# Requirements Document

## Introduction

Azure OpenAI Testing Platform（Azure OpenAI 通用测试平台）是在现有 Azure Realtime Voice Testing Management System 基础上扩展而来的本地开发者工具。现有系统仅支持实时语音（voice）测试，本次扩展将其升级为支持三种测试类型的通用测试平台：语音实时对话（voice）、大语言模型对话（chat）、图像生成（image）。

平台的核心思路是"扩展而非重写"：在已有的 `instances` 表上新增 `type` 字段（取值为 voice | chat | image），用户在创建实例时选择类型，界面根据实例类型路由到对应的测试面板（Playground）。已有的语音实例在数据迁移时默认归为 type=voice，保证向后兼容。三种测试类型共享统一的历史记录（History）与仪表盘（Dashboard），并按测试类型进行筛选与聚合。

本平台是本地部署的开发调试工具，沿用现有技术栈：后端 Python 3.12 + FastAPI + aiosqlite/SQLite（位于 `azure-voice-admin/backend/app/`），前端 TypeScript + React 19 + Vite + Tailwind v4 + Radix UI + recharts + lucide-react（位于 `azure-voice-admin/frontend/src/`）。

### Assumptions（假设）

以下为在澄清阶段确认或基于现有系统约定推导的假设，明确标注为假设：

- **[假设]** 平台不引入身份认证机制，与现有系统保持一致，仅面向本地开发者使用。
- **[假设]** `gpt-5.5`（chat）与 `gpt-image-2`（image）为用户在创建实例时逐实例填写的 Azure OpenAI 部署名称（deployment name），并非硬编码常量；文档中出现的这两个名称仅作示例引用。
- **[假设]** Azure OpenAI API 版本（api-version）可配置，通过环境变量或按实例字段指定，遵循现有系统的配置约定。

## Glossary

- **Testing_Platform**: 本平台的 Web 后端与前端整体，提供 API 与页面服务，是现有 Management_System 的扩展
- **Instance**: 一组 Azure OpenAI 凭据配置（name、endpoint、API key、deployment name、type 等），代表一个可测试的模型部署
- **Instance_Type**: 实例的测试类型字段，取值为 `voice`、`chat` 或 `image`
- **Instance_Store**: 负责持久化存储 Instance 配置的组件（使用 SQLite 的 `instances` 表）
- **Chat_Playground**: 针对 type=chat 实例的多轮对话测试面板
- **Chat_Session**: 一次 LLM 多轮对话会话，关联到某个 chat 类型 Instance，持久化到会话历史
- **Image_Playground**: 针对 type=image 实例的图像生成测试面板
- **Image_Generation**: 一次图像生成请求及其产出结果（含参数、生成的图片文件、用量元数据）
- **Image_Store**: 负责将生成的图片文件持久化到数据目录、并将元数据记录写入数据库的组件
- **Voice_Session**: 现有系统中的一次实时语音对话会话（type=voice）
- **Session_Store**: 负责持久化存储各类会话元数据的组件（使用 SQLite 的 `sessions`、`session_messages`、`session_logs` 表）
- **Token_Tracker**: 负责记录和统计各类测试的 Token/用量消耗的组件
- **Unified_History**: 跨 voice / chat / image 三种测试类型的统一历史记录视图
- **Unified_Dashboard**: 跨三种测试类型聚合用量与统计的统一仪表盘视图
- **Migration_Process**: 在系统启动时对现有数据库结构进行向后兼容升级的过程
- **Azure_OpenAI_API**: 平台按 Instance 凭据调用的 Azure OpenAI 服务端点
- **Web_UI**: 基于 React 的前端管理界面
- **Data_Dir**: 现有系统用于存放持久化数据（SQLite 数据库等）的目录

## Requirements

### Requirement 1: 实例类型管理

**User Story:** As a developer, I want to assign a test type to each Azure instance and be routed to the matching playground, so that I can test voice, chat, and image deployments from one tool.

#### Acceptance Criteria

1. WHEN a user creates a new Instance via the Web_UI, THE Instance_Store SHALL persist the Instance_Type value selected by the user, where the allowed values are `voice`, `chat`, and `image`
2. IF a user submits an Instance without selecting an Instance_Type, THEN THE Testing_Platform SHALL reject the submission and display a validation error indicating that a type is required
3. WHEN a user opens an Instance whose Instance_Type is `voice`, THE Web_UI SHALL route the user to the voice test view
4. WHEN a user opens an Instance whose Instance_Type is `chat`, THE Web_UI SHALL route the user to the Chat_Playground
5. WHEN a user opens an Instance whose Instance_Type is `image`, THE Web_UI SHALL route the user to the Image_Playground
6. WHEN the Testing_Platform displays the instance list, THE Web_UI SHALL show a type badge for each Instance indicating its Instance_Type
7. THE Instance_Store SHALL treat Instance_Type as immutable after creation, and WHERE a user edits an existing Instance, THE Web_UI SHALL disable changing the Instance_Type field
8. WHEN a user filters the instance list by Instance_Type, THE Testing_Platform SHALL display only the Instances matching the selected type

### Requirement 2: LLM 对话测试面板

**User Story:** As a developer, I want a full chat playground for LLM deployments, so that I can run multi-turn conversations with adjustable parameters and streaming responses.

#### Acceptance Criteria

1. WHEN a user sends a message in the Chat_Playground, THE Testing_Platform SHALL call the Azure_OpenAI_API using the selected Instance's credentials and deployment name
2. WHILE the Azure_OpenAI_API returns a streaming response, THE Web_UI SHALL render the assistant reply token-by-token as tokens are received
3. THE Chat_Playground SHALL maintain multi-turn conversation context by sending the accumulated message history with each request
4. THE Chat_Playground SHALL allow the user to set a system prompt, a temperature value, and a max_tokens value before or during a Chat_Session
5. WHEN a user adjusts the temperature parameter, THE Chat_Playground SHALL constrain the value to the range 0 to 2 inclusive
6. WHEN a user adjusts the max_tokens parameter, THE Chat_Playground SHALL constrain the value to a positive integer
7. WHEN a user starts a new conversation in the Chat_Playground, THE Chat_Playground SHALL clear the current conversation context and begin a new Chat_Session

### Requirement 3: 对话会话持久化与用量追踪

**User Story:** As a developer, I want each chat session and its token usage persisted, so that I can review past conversations and compare model usage.

#### Acceptance Criteria

1. WHEN a Chat_Session begins, THE Session_Store SHALL create a session record associated with the chat Instance ID and the Instance_Type `chat`
2. WHEN a message is sent or received in a Chat_Session, THE Session_Store SHALL persist the message with its role (`user` or `assistant`), content, and timestamp to the `session_messages` table
3. WHEN the Azure_OpenAI_API returns token usage data for a chat response, THE Token_Tracker SHALL persist the input tokens and output tokens to the Session_Store associated with the Chat_Session
4. WHEN a user views a Chat_Session in the Unified_History, THE Testing_Platform SHALL display the full ordered message transcript and the recorded token usage
5. WHEN a user deletes a Chat_Session record, THE Session_Store SHALL remove the session metadata and its associated messages from storage
6. IF the Azure_OpenAI_API does not return token usage for a response, THEN THE Token_Tracker SHALL record the usage as zero and THE Testing_Platform SHALL still persist the message content

### Requirement 4: 图像生成测试面板

**User Story:** As a developer, I want an image generation playground with the documented parameters, so that I can test image deployments and generate or edit images.

#### Acceptance Criteria

1. THE Image_Playground SHALL provide the following input controls: a prompt text field, an image size selector, a quality selector with options Low, Medium, and High, a compression level slider ranging from 0 to 100 with a default value of 100, an image format dropdown including at least `png`, a number-of-variations slider with a default value of 1, and an attach-reference-image button
2. WHEN a user submits a generation request, THE Testing_Platform SHALL call the Azure_OpenAI_API using the selected image Instance's credentials, deployment name, and the configured parameters
3. WHERE a user attaches a reference image before submitting, THE Testing_Platform SHALL include the reference image in the request to perform an edit or variation operation
4. WHILE no Image_Generation has been produced in the current Image_Playground view, THE Web_UI SHALL display an empty state with the message "Generate an image to get started"
5. WHEN the Azure_OpenAI_API returns generated images, THE Web_UI SHALL display all returned image variations in the Image_Playground
6. IF a user sets the number-of-variations to a value greater than 1, THEN THE Testing_Platform SHALL request that number of image variations in a single generation request
7. WHEN a user adjusts the compression level slider, THE Image_Playground SHALL constrain the value to the range 0 to 100 inclusive

### Requirement 5: 图像持久化与文件存储

**User Story:** As a developer, I want generated images and their metadata persisted, so that I can review them later in the unified history.

#### Acceptance Criteria

1. WHEN the Azure_OpenAI_API returns generated images, THE Image_Store SHALL save each generated image file to the filesystem under the Data_Dir
2. WHEN an Image_Generation is saved, THE Image_Store SHALL persist a metadata record to the database including the prompt, the generation parameters, the token or image usage returned by Azure_OpenAI_API, the associated Instance ID, and a reference to the saved image file location
3. WHEN a user views an Image_Generation in the Unified_History, THE Testing_Platform SHALL display the generated image, the prompt, and the recorded parameters and usage
4. WHEN a user deletes an Image_Generation record, THE Image_Store SHALL remove both the database metadata record and the associated image files from the Data_Dir
5. IF writing an image file to the Data_Dir fails, THEN THE Testing_Platform SHALL report an error to the user and SHALL avoid persisting a metadata record that references a missing file

### Requirement 6: 统一历史记录

**User Story:** As a developer, I want a unified history across all three test types, so that I can browse and filter past voice, chat, and image tests in one place.

#### Acceptance Criteria

1. WHEN a user navigates to the Unified_History page, THE Testing_Platform SHALL display a paginated list of past tests across the `voice`, `chat`, and `image` types ordered by start time with the most recent first
2. WHEN the Unified_History list is displayed, THE Web_UI SHALL show a type badge for each entry indicating whether it is a voice, chat, or image test
3. WHEN a user filters the Unified_History by test type, THE Testing_Platform SHALL display only the entries matching the selected type
4. WHEN a user filters the Unified_History by Instance, THE Testing_Platform SHALL display only the entries associated with the selected Instance
5. WHEN a user selects an entry from the Unified_History, THE Testing_Platform SHALL display the detail view corresponding to that entry's test type
6. THE Unified_History SHALL preserve access to existing voice session records without data loss after the platform is upgraded

### Requirement 7: 统一仪表盘

**User Story:** As a developer, I want a unified dashboard aggregating usage across all test types, so that I can compare consumption across voice, chat, and image and across instances.

#### Acceptance Criteria

1. WHEN a user navigates to the Unified_Dashboard, THE Testing_Platform SHALL display aggregated token or image usage totals across the `voice`, `chat`, and `image` test types
2. WHEN a user filters the Unified_Dashboard by test type, THE Testing_Platform SHALL recompute and display the aggregated usage limited to the selected type
3. WHEN a user filters the Unified_Dashboard by Instance, THE Testing_Platform SHALL recompute and display the aggregated usage limited to the selected Instance
4. THE Unified_Dashboard SHALL display per-Instance usage totals alongside the overall totals
5. WHERE no test records exist for a selected filter, THE Unified_Dashboard SHALL display a zero-value or empty state rather than an error

### Requirement 8: 向后兼容与数据迁移

**User Story:** As a developer, I want my existing voice instances and sessions preserved, so that upgrading to the platform does not lose or break existing data.

#### Acceptance Criteria

1. WHEN the Testing_Platform starts against a database created by the previous voice-only system, THE Migration_Process SHALL add the Instance_Type column to the `instances` table without dropping existing data
2. WHEN the Migration_Process adds the Instance_Type column, THE Migration_Process SHALL set the Instance_Type of every pre-existing Instance to `voice`
3. WHEN the Migration_Process adds any new tables or columns required for chat and image testing, THE Migration_Process SHALL do so idempotently so that repeated startups do not fail or duplicate schema
4. THE Testing_Platform SHALL continue to support all existing voice testing behavior after the Migration_Process completes
5. IF the Migration_Process encounters an error while altering the schema, THEN THE Testing_Platform SHALL log the error with details and SHALL halt startup rather than operating on a partially migrated database

### Requirement 9: 非功能性需求

**User Story:** As a developer, I want the platform to be consistent, robust, and safe with credentials, so that it integrates cleanly with the existing tool and does not leak secrets.

#### Acceptance Criteria

1. THE Web_UI SHALL present the Chat_Playground, Image_Playground, Unified_History, and Unified_Dashboard using the existing design system (Tailwind v4, Radix UI, lucide-react icons) consistent with the current voice interface
2. IF a call to the Azure_OpenAI_API fails or returns an error status, THEN THE Testing_Platform SHALL capture the error and THE Web_UI SHALL display a readable error message to the user without crashing the current view
3. WHEN the Testing_Platform displays or logs an Instance, THE Testing_Platform SHALL mask the API key showing only the last 4 characters and SHALL avoid writing the full API key to logs or client responses
4. WHERE the Azure OpenAI API version is required for a request, THE Testing_Platform SHALL read the api-version from configuration (environment variable or per-instance field) rather than a hardcoded value
5. THE Testing_Platform SHALL persist all structured data in the existing SQLite database and all generated image files under the Data_Dir, without introducing a separate external datastore

### Requirement 10: 构建与测试验证

**User Story:** As a developer, I want the changes verified via the repository's build and tests, so that the extension does not break the existing system.

#### Acceptance Criteria

1. WHEN backend changes are completed, THE developer SHALL verify the FastAPI backend starts and its tests pass using the repository's Python 3.12 tooling
2. WHEN frontend changes are completed, THE developer SHALL verify the React frontend builds successfully using the repository's Vite/TypeScript build command
3. WHEN new chat or image functionality is added, THE developer SHALL add or update tests covering the new backend endpoints and persistence behavior
4. IF the build or tests fail after a change, THEN THE developer SHALL fix the failures before considering the change complete
