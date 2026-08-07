# Requirements Document

## Introduction

Azure Realtime Voice Testing Management System（Azure 实时语音测试管理系统）是一个本地部署的管理面板工具，帮助开发者管理多个 Azure OpenAI Realtime API 实例配置、发起实时语音对话测试、追踪 Token 消耗和费用、查看调试日志，并管理历史会话记录。

每个用户可以创建多个 Azure 实例配置（不同的 endpoint + key + model 组合），每个实例可以独立发起语音对话，对应到不同的 LiveKit 房间。系统面向开发者本地调试场景。

## Glossary

- **Management_System**: 本系统的 Web 管理后端，提供 API 和页面服务
- **Instance**: 一组 Azure OpenAI Realtime 凭据配置（endpoint、API key、deployment name），代表一个可测试的模型部署
- **Instance_Store**: 负责持久化存储多个 Instance 配置的组件（使用 SQLite）
- **Voice_Session**: 一次实时语音对话会话，关联到某个 Instance，包含从创建房间到断开连接的完整生命周期
- **Agent_Worker**: 基于 livekit-agents 的后端进程，根据指定 Instance 的凭据连接 Azure OpenAI Realtime API 并处理语音交互
- **Token_Tracker**: 负责记录和统计每次会话中 Azure API 的 Token 消耗量的组件
- **Debug_Logger**: 负责捕获和展示 WebSocket 事件、请求/响应载荷和错误信息的组件
- **Session_Store**: 负责持久化存储历史会话元数据的组件（使用 SQLite）
- **Web_UI**: 基于 HTML/JS 的前端管理界面

## Requirements

### Requirement 1: 多实例配置管理

**User Story:** As a developer, I want to manage multiple Azure OpenAI deployment configurations, so that I can test different models, endpoints, and API keys without re-editing config files.

#### Acceptance Criteria

1. WHEN a user creates a new Instance via the Web_UI, THE Instance_Store SHALL persist the configuration (name, endpoint, API key, deployment name, optional description) to SQLite storage
2. WHEN a user navigates to the instance list page, THE Management_System SHALL display all saved Instances with their name, endpoint, deployment name, and creation time
3. WHEN a user edits an existing Instance, THE Instance_Store SHALL update the stored configuration and confirm the save operation
4. WHEN a user deletes an Instance, THE Instance_Store SHALL remove the configuration and THE Management_System SHALL prevent deletion if the Instance has an active Voice_Session
5. IF the user submits an Instance with an empty endpoint or empty API key, THEN THE Management_System SHALL reject the submission and display a validation error
6. WHEN Instance details are displayed in the Web_UI, THE Management_System SHALL mask the API key field showing only the last 4 characters
7. EACH Instance SHALL have a unique user-defined name to distinguish it from other Instances

### Requirement 2: 实时语音对话房间

**User Story:** As a developer, I want to start a real-time voice conversation targeting a specific Azure instance, so that I can test different model deployments independently.

#### Acceptance Criteria

1. WHEN a user selects an Instance and clicks "Start Session", THE Management_System SHALL create a new LiveKit room with a unique name and generate a join token for the user
2. WHEN a Voice_Session is initiated, THE Agent_Worker SHALL connect to Azure OpenAI Realtime API using the selected Instance's credentials
3. WHILE a Voice_Session is active, THE Web_UI SHALL display the connection status (connecting, connected, agent speaking, user speaking, disconnected) and indicate which Instance is being used
4. WHEN a user clicks "End Session", THE Management_System SHALL disconnect the user from the room and signal the Agent_Worker to terminate
5. IF the selected Instance's credentials are invalid, THEN THE Agent_Worker SHALL report the error and THE Web_UI SHALL display the error details
6. THE Management_System SHALL support multiple concurrent Voice_Sessions using different Instances, each in a separate LiveKit room
7. WHILE a Voice_Session is active, THE Agent_Worker SHALL stream audio bidirectionally between the user microphone and Azure OpenAI Realtime API via LiveKit

### Requirement 3: Token 消耗与计费统计

**User Story:** As a developer, I want to see how many tokens each voice session consumes grouped by instance, so that I can estimate costs and compare usage across different deployments.

#### Acceptance Criteria

1. WHILE a Voice_Session is active, THE Token_Tracker SHALL capture token usage data (input tokens, output tokens) from Azure API response events
2. WHEN a Voice_Session ends, THE Token_Tracker SHALL persist the total token counts (input tokens, output tokens) to the Session_Store, associated with both the session ID and the Instance ID
3. WHEN a user views the dashboard, THE Management_System SHALL display cumulative token usage per Instance and overall totals
4. WHEN a user views a specific session detail, THE Management_System SHALL display the token counts for that individual session
5. WHEN a user views an Instance detail page, THE Management_System SHALL display the total token consumption across all sessions for that Instance

### Requirement 4: 调试控制台

**User Story:** As a developer, I want to see real-time logs of WebSocket events and API interactions during a voice session, so that I can debug issues with specific Azure deployments.

#### Acceptance Criteria

1. WHILE a Voice_Session is active, THE Debug_Logger SHALL capture WebSocket events (connection open, message received, message sent, connection close, errors) with timestamps
2. WHILE a Voice_Session is active, THE Web_UI SHALL display log entries in real-time as they are captured by the Debug_Logger
3. WHEN a log entry is captured, THE Debug_Logger SHALL include the event type, timestamp, direction (inbound/outbound), and payload summary
4. WHEN a user clicks on a log entry in the Web_UI, THE Management_System SHALL display the full payload content in a formatted JSON view
5. IF a WebSocket error occurs during a Voice_Session, THEN THE Debug_Logger SHALL capture the error details and THE Web_UI SHALL highlight the error entry visually
6. WHEN a Voice_Session ends, THE Debug_Logger SHALL persist the session logs to the Session_Store for later review
7. THE Web_UI SHALL support filtering log entries by event type (e.g., session.update, response.audio.delta, error)

### Requirement 5: 会话历史管理

**User Story:** As a developer, I want to browse past voice sessions with their metadata grouped by instance, so that I can review previous test results and compare performance across deployments.

#### Acceptance Criteria

1. WHEN a user navigates to the session history page, THE Management_System SHALL display a paginated list of past sessions ordered by start time (most recent first)
2. THE Session_Store SHALL record the following metadata for each Voice_Session: session ID, Instance ID, room name, start time, end time, duration, total input tokens, total output tokens, and final status (completed, error, cancelled)
3. WHEN a user selects a session from the history list, THE Management_System SHALL display the session detail including metadata and saved debug logs
4. WHEN a user requests to delete a session record, THE Session_Store SHALL remove the session metadata and associated debug logs from storage
5. THE Web_UI SHALL support filtering the session history list by Instance name
6. WHEN the session history list is displayed, THE Web_UI SHALL show a summary row for each session including: Instance name, start time, duration, token count, and status indicator

### Requirement 6: 系统启动与本地部署

**User Story:** As a developer, I want to start the entire management system with a single command, so that I can quickly begin testing without complex setup.

#### Acceptance Criteria

1. WHEN the user runs the start command, THE Management_System SHALL initialize the SQLite database, start the web server, and start the Agent_Worker process
2. THE Management_System SHALL serve the Web_UI on a single configurable port (default 8090)
3. WHEN the Management_System starts, THE Management_System SHALL verify that a LiveKit server is reachable at the configured URL
4. IF the LiveKit server is unreachable at startup, THEN THE Management_System SHALL log a warning and allow startup to continue with degraded functionality (session creation disabled)
5. THE Management_System SHALL store all persistent data in a single SQLite database file in the project directory
6. THE Management_System SHALL dynamically spawn Agent_Worker processes per Voice_Session, passing the corresponding Instance credentials at runtime
