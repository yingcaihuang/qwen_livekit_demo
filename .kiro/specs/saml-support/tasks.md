# Implementation Plan: SAML Support

## Overview

为现有平台新增 SAML 2.0 SP 能力，包括后端 SAML 协议处理服务、API 端点、数据库 schema 扩展，以及前端配置面板和登录页多 SSO 入口。实现基于 `python3-saml` 库，复用现有 `provisioning_service` 进行用户开通。

## Tasks

- [x] 1. 数据库 Schema 与依赖配置
  - [x] 1.1 扩展 schema.sql，新增 `saml_config` 和 `saml_login_state` 两张表
    - 添加 `saml_config` 表（单例行模式，包含 IdP/SP 配置字段）
    - 添加 `saml_login_state` 表（存储 AuthnRequest ID 和 RelayState）
    - _Requirements: 1.1, 3.2_

  - [x] 1.2 更新 `requirements.txt`，添加 `python3-saml>=1.16.0` 依赖
    - _Requirements: 11.1, 11.2_

- [x] 2. SAML 核心服务层
  - [x] 2.1 创建 `app/services/saml_service.py`，实现基础设施函数
    - 实现 `prepare_request_from_fastapi()` 将 FastAPI Request 转换为 python3-saml 格式
    - 实现 `load_saml_settings()` 从数据库加载配置并构建 settings dict
    - 实现 `build_saml_settings()` 构建 python3-saml 所需的完整 settings 结构
    - 实现 `SAMLValidationError` 自定义异常类
    - _Requirements: 1.1, 11.5_

  - [x] 2.2 实现 `saml_service.py` 中的 SP Metadata 生成函数
    - 实现 `generate_sp_metadata()` 生成符合 SAML 2.0 Metadata schema 的 SP Metadata XML
    - 包含 EntityDescriptor、AssertionConsumerService (HTTP-POST)、SingleLogoutService (HTTP-Redirect)、NameIDFormat
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 2.3 实现 `saml_service.py` 中的 IdP Metadata 解析函数
    - 实现 `parse_idp_metadata(url, xml)` 支持从 URL 获取或直接解析 XML
    - 提取 idp_entity_id、idp_sso_url、idp_slo_url、idp_x509_cert
    - 缺少必要字段时 raise ValueError
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 2.4 实现 `saml_service.py` 中的登录流程函数
    - 实现 `initiate_login()` 生成 AuthnRequest，存储 request_id 到 saml_login_state，返回 IdP 重定向 URL
    - 实现 `process_acs()` 处理 ACS 回调：签名验证、时间条件、Audience、InResponseTo 校验
    - 支持 SP-Initiated（验证 InResponseTo）和 IdP-Initiated（跳过 InResponseTo）两种模式
    - ACS 成功后删除已消费的 request_id，清理过期记录（5 分钟 TTL）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 5.1, 5.2, 5.3_

  - [x] 2.5 实现 `saml_service.py` 中的安全验证函数
    - 实现 `validate_relay_state()` 仅接受相对路径或同源 URL，拒绝外部 URL
    - 实现 `validate_x509_cert()` 验证 PEM 格式 X.509 证书且 <= 64KB
    - 实现 XXE 预检：在传入 python3-saml 前检测 `<!DOCTYPE` 和 `<!ENTITY`
    - _Requirements: 10.2, 10.4, 10.5_

  - [ ]* 2.6 编写 `tests/test_saml_service.py` 单元测试
    - 测试 IdP Metadata 解析（有效/无效 XML）
    - 测试 RelayState 验证（相对路径通过、外部 URL 拒绝）
    - 测试 X.509 证书验证（有效 PEM 通过、无效拒绝）
    - 测试 XXE 检测（含 DOCTYPE 拒绝）
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 10.2, 10.4, 10.5_

  - [ ]* 2.7 编写 Property Test：IdP Metadata 解析正确性（Property 1 & 2）
    - **Property 1: IdP Metadata Parsing Extracts Required Fields**
    - **Property 2: Invalid Metadata Rejection**
    - **Validates: Requirements 1.3, 1.4, 1.5, 1.6**

  - [ ]* 2.8 编写 Property Test：RelayState 验证与 X.509 验证（Property 8 & 9）
    - **Property 8: RelayState Rejects External URLs**
    - **Property 9: X.509 Certificate Validation**
    - **Validates: Requirements 10.4, 10.5**

  - [ ]* 2.9 编写 Property Test：XXE 拒绝与配置字段验证（Property 10 & 11）
    - **Property 10: XXE Rejection**
    - **Property 11: SAML Config Required Field Validation**
    - **Validates: Requirements 10.2, 8.4, 8.5**

- [x] 3. Checkpoint - 确保 SAML 服务层测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. SAML 公开 API 端点
  - [x] 4.1 创建 `app/api/saml.py`，实现 SAML 公开路由
    - `GET /api/saml/metadata` — 返回 SP Metadata XML（Content-Type: application/samlmetadata+xml）
    - `GET /api/saml/login` — 发起 SP-Initiated 登录，重定向到 IdP
    - `POST /api/saml/acs` — 接收并处理 SAMLResponse，完成用户开通和会话创建
    - `GET /api/saml/slo` — SP-Initiated 登出
    - `GET /api/saml/sls` — 处理 IdP 发起的 LogoutRequest/Response
    - _Requirements: 2.1, 2.5, 3.1, 3.3, 4.1, 5.4, 5.5, 5.6, 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 4.2 在 ACS 处理中集成 `provisioning_service.provision_sso_user`
    - 从 SAML Assertion 提取 NameID、email、groups 属性
    - 调用 `provision_sso_user` 时传入 `auth_source='saml'`
    - 使用 `auth_service.create_session()` 创建会话并设置 Cookie
    - 扩展 `provision_sso_user` 函数签名支持 `auth_source` 参数
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - [x] 4.3 修改 `app/api/sso.py`，扩展 `public-config` 端点返回 `saml_login_enabled` 字段
    - 查询 `saml_config` 表的 `login_button_enabled` 状态
    - 在返回的 JSON 中增加 `saml_login_enabled` 布尔字段
    - _Requirements: 7.7_

  - [x] 4.4 在 `app/main.py` 中注册 SAML 路由
    - 引入并挂载 `saml.router`（前缀 `/api/saml`）
    - 引入并挂载 `admin_saml.router`（前缀 `/api/admin/saml-config`）
    - _Requirements: 2.1, 4.1_

- [x] 5. SAML 管理 API 端点
  - [x] 5.1 创建 `app/api/admin_saml.py`，实现 SAML 配置管理路由
    - `GET /api/admin/saml-config` — 获取 SAML 配置（需 `sso:manage` 权限）
    - `PUT /api/admin/saml-config` — 保存 SAML 配置（验证必填字段、证书格式）
    - `POST /api/admin/saml-config/parse-metadata` — 解析 IdP Metadata（URL 或 XML）
    - 权限校验：无 `sso:manage` 返回 403
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ]* 5.2 编写 `tests/test_saml_api.py` API 集成测试
    - 测试 SP Metadata 端点返回有效 XML
    - 测试管理 API 权限校验（无权限返回 403）
    - 测试配置保存验证（缺少必填字段返回 422）
    - 测试 parse-metadata 端点
    - _Requirements: 2.1, 8.4, 8.5, 8.7_

  - [ ]* 5.3 编写 Property Test：SP Metadata 生成完整性（Property 3）
    - **Property 3: SP Metadata Generation Completeness**
    - **Validates: Requirements 2.2, 2.3, 2.4**

  - [ ]* 5.4 编写 Property Test：InResponseTo 单次消费（Property 7）
    - **Property 7: InResponseTo Single-Use Consumption**
    - **Validates: Requirements 4.6, 4.7, 4.8, 10.3**

- [x] 6. Checkpoint - 确保后端所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. 前端 SAML 配置面板
  - [x] 7.1 创建 `frontend/src/components/admin/SamlConfigPanel.tsx` 组件
    - IdP Metadata URL 输入 + "获取" 按钮（调用 parse-metadata API 自动填充）
    - IdP Metadata XML 手动输入 textarea
    - IdP Entity ID、SSO URL、SLO URL、签名证书字段
    - SP Entity ID 配置
    - Groups Attribute 名称输入
    - NameID 格式下拉选择
    - "显示 SAML 入口" 开关
    - SP Metadata 端点 URL 展示 + 复制按钮
    - 保存按钮调用 `PUT /api/admin/saml-config`
    - _Requirements: 8.1, 8.2, 8.3, 8.6_

  - [x] 7.2 修改 `frontend/src/pages/admin/SsoConfigPage.tsx`，重构为 Tab 结构
    - 使用 shadcn/ui Tabs 组件，包含 "OIDC" 和 "SAML" 两个 Tab
    - OIDC Tab 保留现有配置内容不变
    - SAML Tab 嵌入 SamlConfigPanel 组件
    - _Requirements: 8.1_

- [x] 8. 前端登录页多 SSO 入口
  - [x] 8.1 修改 `frontend/src/pages/LoginPage.tsx`，支持多 SSO 入口
    - 扩展 SSO 公开配置接口响应类型，增加 `saml_login_enabled` 字段
    - 根据 `saml_login_enabled` 条件渲染 SAML 登录按钮（href="/api/saml/login"）
    - OIDC 和 SAML 按钮并列显示，两者之间可加分隔线
    - 仅本地登录启用时仅显示表单
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [ ]* 8.2 编写前端组件测试：Login Page SSO 按钮可见性（Property 12）
    - **Property 12: Login Page SSO Button Visibility**
    - 测试所有 (oidc_enabled, saml_enabled) 组合下按钮渲染正确
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6**

- [x] 9. Final Checkpoint - 全部测试通过并验证集成
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- `python3-saml` 依赖系统级 `xmlsec1` 库，需确保开发/部署环境已安装
- `provision_sso_user` 函数需新增 `auth_source` 可选参数以区分 SAML 用户
- 前端使用 shadcn/ui 组件库保持 UI 一致性

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.5"] },
    { "id": 3, "tasks": ["2.4", "2.6", "2.7", "2.8", "2.9"] },
    { "id": 4, "tasks": ["4.1", "5.1"] },
    { "id": 5, "tasks": ["4.2", "4.3", "4.4", "5.2", "5.3"] },
    { "id": 6, "tasks": ["5.4"] },
    { "id": 7, "tasks": ["7.1"] },
    { "id": 8, "tasks": ["7.2", "8.1"] },
    { "id": 9, "tasks": ["8.2"] }
  ]
}
```
