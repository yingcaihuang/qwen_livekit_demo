# Requirements Document

## Introduction

本功能为现有的 Azure OpenAI 测试平台新增 SAML 2.0 单点登录支持。平台已具备完整的 OIDC SSO 实现（含 PKCE、logout、SCIM v2）、本地账号登录、RBAC 角色体系与组→角色映射。本次新增：

1. SAML 2.0 SP（Service Provider）能力，支持 SP-Initiated 和 IdP-Initiated 两种登录流程。
2. SAML 与现有 OIDC 并存，登录页可同时展示多个 SSO 入口按钮。
3. SAML Assertion 中的 groups attribute 复用现有 group_role_mappings 表进行角色映射。
4. 管理后台新增 SAML 配置面板，与 OIDC 配置面板并列。
5. SP Metadata 端点，供 IdP（Azure AD、Okta、OneLogin 等）快速配置信任关系。

本功能不修改现有 OIDC 登录逻辑，不改变业务功能，仅扩展认证方式。

## Glossary

- **Auth_System（鉴权系统）**：平台后端鉴权与授权子系统，负责登录、会话、权限校验。
- **SAML_SP（SAML 服务提供方）**：本平台作为 SAML 2.0 Service Provider，接收并验证 IdP 签发的 SAML Assertion。
- **SAML_IdP（SAML 身份提供方）**：外部身份提供方（如 Azure AD、Okta、OneLogin），签发 SAML Assertion。
- **SAML_Config（SAML 配置）**：数据库中存储的 SAML 连接参数，包括 IdP Metadata URL、Entity ID、证书、端点等。
- **SP_Metadata（SP 元数据）**：本平台生成的 SAML SP Metadata XML，包含 Entity ID、ACS URL、签名证书等，供 IdP 导入配置。
- **ACS_Endpoint（断言消费端点）**：Assertion Consumer Service URL，接收 IdP POST 回来的 SAML Response。
- **SLO_Endpoint（单点登出端点）**：Single Logout Service URL，处理 SAML 登出请求与响应。
- **SAML_Assertion（SAML 断言）**：IdP 签发的 XML 安全令牌，包含用户身份、属性与签名。
- **SP_Initiated_Flow（SP 发起流程）**：用户从本平台发起 SAML AuthnRequest 跳转到 IdP 进行认证。
- **IdP_Initiated_Flow（IdP 发起流程）**：用户从 IdP 门户直接发起登录，IdP 将未经 AuthnRequest 的 SAML Response POST 到本平台 ACS。
- **RelayState**：SAML 流程中用于传递登录后跳转目标 URL 的参数。
- **Group_Role_Mapping（组→角色映射）**：数据库中维护的 IdP 组名到平台角色的映射记录（已有表结构，SAML 复用）。
- **SSO_User（SSO 用户）**：通过 OIDC 或 SAML 登录、由系统自动开通的账号。
- **Session_Cookie（会话 Cookie）**：httpOnly + Secure + SameSite 的会话凭据 Cookie。
- **SAML_Login_State（SAML 登录状态）**：SP-Initiated 流程中临时存储的 AuthnRequest ID，用于防重放校验。

## Requirements

### 需求 1：SAML 配置数据存储

**User Story:** 作为超级管理员，我希望平台能持久化 SAML IdP 连接配置，以便系统启动后可利用该配置完成 SAML 登录流程。

#### Acceptance Criteria

1. THE Auth_System SHALL 在数据库中维护 SAML_Config，包含以下字段：IdP Entity ID、IdP SSO URL、IdP SLO URL、IdP 签名证书（X.509 PEM）、SP Entity ID、groups attribute 名称、NameID 格式、签名算法偏好、以及"是否在登录页显示 SAML 入口"开关。
2. THE Auth_System SHALL 支持通过 IdP Metadata URL 或直接上传 IdP Metadata XML 两种方式导入 IdP 配置参数。
3. WHEN 管理员提供 IdP Metadata URL，THE Auth_System SHALL 从该 URL 获取 Metadata XML 并自动解析出 IdP Entity ID、SSO URL、SLO URL 与签名证书。
4. WHEN 管理员直接上传 IdP Metadata XML 内容，THE Auth_System SHALL 解析该 XML 并提取 IdP Entity ID、SSO URL、SLO URL 与签名证书。
5. IF IdP Metadata URL 不可达或返回无效 XML，THEN THE Auth_System SHALL 返回明确的错误提示并拒绝保存。
6. IF IdP Metadata XML 缺少必要的 SSO Binding 或签名证书，THEN THE Auth_System SHALL 返回校验错误并拒绝保存。

### 需求 2：SP Metadata 端点

**User Story:** 作为平台管理员，我希望平台提供 SP Metadata 端点，以便我能将 SP 信息快速导入到 IdP 完成信任配置。

#### Acceptance Criteria

1. THE SAML_SP SHALL 在 `/api/saml/metadata` 路径上提供 SP_Metadata XML 端点，无需认证即可访问。
2. THE SP_Metadata SHALL 包含 SP Entity ID、ACS_Endpoint URL（HTTP-POST binding）、SLO_Endpoint URL（HTTP-Redirect binding）、以及 NameID Format 声明。
3. WHERE SAML_Config 中配置了 SP 签名证书，THE SP_Metadata SHALL 包含该证书的 KeyDescriptor（用途为 signing）。
4. THE SP_Metadata SHALL 使用标准 SAML 2.0 Metadata schema（`urn:oasis:names:tc:SAML:2.0:metadata`）生成有效 XML。
5. WHEN IdP 管理员访问 SP_Metadata 端点，THE SAML_SP SHALL 返回 Content-Type 为 `application/samlmetadata+xml` 的响应。

### 需求 3：SP-Initiated 登录流程

**User Story:** 作为企业用户，我希望点击登录页的 SAML 按钮后被跳转到企业 IdP 完成认证，以便使用企业身份登录平台。

#### Acceptance Criteria

1. WHEN 用户点击登录页的 SAML 入口按钮，THE SAML_SP SHALL 生成包含唯一 ID 与 ACS URL 的 AuthnRequest XML。
2. WHEN SAML_SP 生成 AuthnRequest，THE SAML_SP SHALL 将该 AuthnRequest 的 ID 存储到 SAML_Login_State 中，设置有效期为 5 分钟。
3. THE SAML_SP SHALL 使用 HTTP-Redirect Binding（GET 请求）将 AuthnRequest 通过 URL 参数发送至 IdP SSO URL，对 SAMLRequest 参数进行 Deflate 压缩与 Base64 编码。
4. WHEN SAML_SP 发起 AuthnRequest，THE SAML_SP SHALL 在 RelayState 参数中携带用户原始请求路径（若有），以便登录完成后跳转回原页面。
5. WHERE SAML_Config 中配置了 SP 签名私钥，THE SAML_SP SHALL 对 AuthnRequest 进行 XML 签名。

### 需求 4：SAML Response 接收与验证

**User Story:** 作为系统安全负责人，我希望平台严格验证 IdP 返回的 SAML Response，以确保认证数据的真实性与完整性。

#### Acceptance Criteria

1. THE SAML_SP SHALL 在 `/api/saml/acs` 路径上提供 ACS_Endpoint，接受 HTTP-POST 请求中的 SAMLResponse 参数。
2. WHEN SAML_SP 收到 SAMLResponse，THE SAML_SP SHALL 对 Base64 解码后的 XML 进行 XML 签名验证，使用 SAML_Config 中配置的 IdP 签名证书。
3. IF SAMLResponse 的 XML 签名验证失败，THEN THE SAML_SP SHALL 拒绝本次登录并返回签名校验失败提示。
4. WHEN SAML_SP 验证签名通过，THE SAML_SP SHALL 校验 Assertion 的 Conditions 元素，包括 NotBefore、NotOnOrAfter 时间窗口以及 AudienceRestriction 是否匹配 SP Entity ID。
5. IF Assertion 的时间条件不满足或 Audience 不匹配，THEN THE SAML_SP SHALL 拒绝本次登录并返回条件校验失败提示。
6. WHEN 该 SAMLResponse 属于 SP-Initiated 流程，THE SAML_SP SHALL 校验 Response 的 InResponseTo 属性是否与 SAML_Login_State 中存储的某个 AuthnRequest ID 匹配。
7. IF InResponseTo 与任何已存储的 AuthnRequest ID 均不匹配或该 ID 已过期，THEN THE SAML_SP SHALL 拒绝本次登录并返回请求匹配失败提示。
8. WHEN InResponseTo 校验通过，THE SAML_SP SHALL 从 SAML_Login_State 中删除该已消费的 AuthnRequest ID，防止重放。
9. THE SAML_SP SHALL 允许 IdP 签名证书时钟偏差不超过 120 秒（可配置），以容忍合理的时钟差异。

### 需求 5：IdP-Initiated 登录流程

**User Story:** 作为企业用户，我希望从企业 IdP 门户直接点击平台入口即可登录，无需先访问平台登录页。

#### Acceptance Criteria

1. WHEN SAML_SP 收到不包含 InResponseTo 属性的 SAMLResponse，THE SAML_SP SHALL 将其视为 IdP-Initiated 流程并跳过 InResponseTo 校验。
2. WHEN 处理 IdP-Initiated SAMLResponse，THE SAML_SP SHALL 仍执行 XML 签名验证、时间条件校验与 Audience 校验。
3. IF IdP-Initiated SAMLResponse 的签名、时间或 Audience 校验失败，THEN THE SAML_SP SHALL 拒绝本次登录并返回相应错误提示。
4. WHEN IdP-Initiated 登录验证通过，THE SAML_SP SHALL 按需求 6 的流程完成用户开通与会话创建。
5. WHERE SAMLResponse 携带 RelayState 参数，THE SAML_SP SHALL 在登录完成后将用户重定向到 RelayState 指定的相对路径。
6. WHERE SAMLResponse 未携带 RelayState，THE SAML_SP SHALL 在登录完成后将用户重定向到平台默认首页。

### 需求 6：SAML 用户自动开通与角色赋予

**User Story:** 作为通过 SAML 首次登录的用户，我希望系统自动为我创建平台账号并按分组赋予角色，以便登录后立即拥有相应权限。

#### Acceptance Criteria

1. WHEN SAML Assertion 验证通过，THE Auth_System SHALL 从 Assertion 的 Subject/NameID 中提取用户唯一标识。
2. WHEN 本地不存在该 NameID 对应的 SSO_User，THE Auth_System SHALL 自动创建本地账号，auth_source 设为 `saml`，sso_subject 存储 NameID 值。
3. WHEN 创建或更新 SAML SSO_User，THE Auth_System SHALL 从 Assertion 的 AttributeStatement 中按 SAML_Config 配置的 groups attribute 名称提取用户分组列表。
4. WHEN Auth_System 获取到 SAML 用户分组列表，THE Auth_System SHALL 使用现有 group_role_mappings 表计算并赋予该用户角色。
5. IF SAML 用户的所有分组均未匹配到 group_role_mappings，THEN THE Auth_System SHALL 为该用户赋予 `viewer` 角色。
6. WHEN 已存在的 SAML SSO_User 再次登录且其分组发生变化，THE Auth_System SHALL 依据当前分组与 group_role_mappings 重新计算并更新该用户角色（前提是 role_override 未设置）。
7. WHEN SAML 用户开通或更新完成，THE Auth_System SHALL 创建认证会话并通过 Session_Cookie 下发会话凭据。
8. WHERE Assertion 中包含 email 属性或 displayName 属性，THE Auth_System SHALL 将其同步至本地用户记录。

### 需求 7：登录页多 SSO 入口展示

**User Story:** 作为平台用户，我希望登录页同时展示所有已启用的 SSO 入口，以便我选择合适的认证方式登录。

#### Acceptance Criteria

1. WHERE SAML_Config 中"显示 SAML 入口"开关处于开启状态，THE 登录页 SHALL 展示 SAML 登录按钮。
2. WHERE sso_config 中"显示统一认证入口"开关处于开启状态，THE 登录页 SHALL 同时展示 OIDC 登录按钮。
3. THE 登录页 SHALL 在本地登录表单下方以独立按钮形式分别展示每个已启用的 SSO 入口（OIDC 与 SAML）。
4. WHEN 仅 SAML 启用而 OIDC 未启用，THE 登录页 SHALL 仅展示本地登录表单与 SAML 按钮。
5. WHEN 仅 OIDC 启用而 SAML 未启用，THE 登录页 SHALL 仅展示本地登录表单与 OIDC 按钮（保持现有行为不变）。
6. WHEN SAML 与 OIDC 均未启用，THE 登录页 SHALL 仅展示本地登录表单。
7. THE 前端 SHALL 通过调用一个公开的配置接口获取当前启用的 SSO 入口列表，该接口无需认证。

### 需求 8：SAML 管理后台配置界面

**User Story:** 作为超级管理员，我希望在 SSO 配置页面中管理 SAML 配置，以便无需改代码即可调整 SAML 接入。

#### Acceptance Criteria

1. WHERE 用户具备 `sso:manage` 能力，THE Auth_System SHALL 在 SSO 配置页面中展示 SAML 配置面板，与现有 OIDC 配置面板并列（使用 Tab 或 Card 分区）。
2. THE SAML 配置面板 SHALL 包含以下可编辑字段：IdP Metadata URL、IdP Metadata XML（手动输入）、IdP Entity ID、IdP SSO URL、IdP SLO URL、IdP 签名证书、SP Entity ID、groups attribute 名称、NameID 格式选择、以及"是否在登录页显示 SAML 入口"开关。
3. WHEN 管理员输入 IdP Metadata URL 并点击"获取"，THE 管理界面 SHALL 调用后端解析接口并将解析结果自动填充到对应字段。
4. WHEN 管理员保存 SAML_Config，THE Auth_System SHALL 对配置进行完整性校验：IdP Entity ID、IdP SSO URL、IdP 签名证书为必填。
5. IF 管理员提交的 SAML_Config 缺少必填字段，THEN THE Auth_System SHALL 拒绝保存并返回具体的校验错误信息。
6. THE SAML 配置面板 SHALL 展示当前 SP Metadata 端点 URL，并提供复制按钮方便管理员将其配置到 IdP。
7. IF 不具备 `sso:manage` 的用户请求 SAML 配置管理接口，THEN THE Auth_System SHALL 返回 HTTP 403。

### 需求 9：SAML 登出

**User Story:** 作为通过 SAML 登录的用户，我希望登出时平台清除本地会话，并支持 IdP 发起的全局登出。

#### Acceptance Criteria

1. WHEN SAML 用户请求登出，THE Auth_System SHALL 使本地会话失效并清除 Session_Cookie。
2. WHERE SAML_Config 中配置了 IdP SLO URL，WHEN SAML 用户登出，THE SAML_SP SHALL 向 IdP 发送 SAML LogoutRequest（HTTP-Redirect Binding）。
3. WHEN SAML_SP 收到来自 IdP 的 LogoutRequest，THE SAML_SP SHALL 验证请求签名后使对应用户的本地会话失效，并向 IdP 返回 LogoutResponse。
4. IF IdP LogoutRequest 的签名验证失败，THEN THE SAML_SP SHALL 拒绝该登出请求并返回错误状态。
5. WHERE SAML_Config 未配置 IdP SLO URL，WHEN 用户登出，THE Auth_System SHALL 仅清除本地会话而不尝试联系 IdP。

### 需求 10：安全防护

**User Story:** 作为系统安全负责人，我希望 SAML 实现具备充分的安全防护，以防止常见的 SAML 攻击向量。

#### Acceptance Criteria

1. THE SAML_SP SHALL 对所有接收到的 SAMLResponse 进行 XML Canonical 化处理后再进行签名验证，防止 XML 签名包装攻击。
2. THE SAML_SP SHALL 拒绝包含 DTD 声明或外部实体引用的 SAML XML，防止 XXE 攻击。
3. THE SAML_SP SHALL 对 SP-Initiated 流程中每个 AuthnRequest ID 仅允许消费一次，防止 SAML Response 重放。
4. WHEN SAML_SP 存储 IdP 签名证书，THE Auth_System SHALL 验证该证书为有效的 X.509 格式，且长度不超过合理上限（64KB）。
5. THE SAML_SP SHALL 对 RelayState 参数进行验证，仅允许相对路径或同源 URL，拒绝外部 URL 重定向。
6. WHEN Auth_System 记录 SAML 相关日志，THE Auth_System SHALL 不将完整的 SAML Assertion XML 或用户敏感属性写入日志，仅记录 NameID 与操作结果。

### 需求 11：主流 IdP 兼容性

**User Story:** 作为平台管理员，我希望 SAML 实现兼容主流 IdP，以便企业用户可使用其现有身份基础设施。

#### Acceptance Criteria

1. THE SAML_SP SHALL 支持 HTTP-POST Binding 接收 SAMLResponse（Azure AD、Okta、OneLogin 的默认行为）。
2. THE SAML_SP SHALL 支持 HTTP-Redirect Binding 发送 AuthnRequest（主流 IdP 的通用要求）。
3. THE SAML_SP SHALL 支持 NameID 格式包括 `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress`、`urn:oasis:names:tc:SAML:2.0:nameid-format:persistent` 与 `urn:oasis:names:tc:SAML:2.0:nameid-format:unspecified`。
4. THE SAML_SP SHALL 支持解析 Assertion 中的 AttributeStatement，按 SAML_Config 中配置的 attribute 名称提取 groups 值（适配不同 IdP 的 attribute 命名差异）。
5. THE SAML_SP SHALL 支持 SHA-256 签名算法（`http://www.w3.org/2001/04/xmldsig-more#rsa-sha256`）作为 IdP Response 签名的验证算法。
6. WHERE IdP 对 Response 整体签名而非对单个 Assertion 签名，THE SAML_SP SHALL 接受 Response 级别签名作为有效签名。
7. WHERE IdP 仅对 Assertion 签名而非对 Response 整体签名，THE SAML_SP SHALL 接受 Assertion 级别签名作为有效签名。
