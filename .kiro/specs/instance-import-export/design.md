# 实例导入/导出 Bugfix Design

## Overview

当前实例管理系统缺少批量导入/导出功能，用户在跨环境迁移配置时只能手动逐个创建，效率低且易出错。本修复通过在后端新增 `POST /api/instances/export` 和 `POST /api/instances/import` 两个 API 端点，前端新增导出对话框和导入对话框（含预览/选择/冲突处理），实现 JSON 格式的批量实例配置迁移。导出支持选择性导出和 API Key 安全控制，导入支持文件预览、选择性导入、冲突策略和字段校验。

## Glossary

- **Bug_Condition (C)**: 用户尝试批量导入或导出实例配置时，系统没有对应功能端点和 UI 入口
- **Property (P)**: 系统应提供完整的导入/导出 API 和 UI，支持选择性操作、安全控制和冲突处理
- **Preservation**: 现有的单实例 CRUD、列表筛选、批量删除、脱敏展示等功能必须保持不变
- **InstanceService**: `backend/app/services/instance_service.py` 中的实例管理业务逻辑类
- **instances router**: `backend/app/api/instances.py` 中的 FastAPI 路由，前缀 `/api/instances`
- **InstancesPage**: `frontend/src/pages/InstancesPage.tsx` 中的实例列表页面组件
- **冲突策略 (ConflictStrategy)**: 导入时遇到同名实例的处理方式 — "skip"（跳过）或 "update"（覆盖更新）

## Bug Details

### Bug Condition

当用户需要将实例配置在不同环境间迁移、或批量备份/恢复实例数据时，系统没有提供任何导入/导出功能端点和 UI 入口。用户被迫逐个手动复制配置信息，过程低效且容易遗漏字段。

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type UserAction
  OUTPUT: boolean

  RETURN (input.action == "export" AND input.targetInstances.length >= 1)
         OR (input.action == "import" AND input.jsonPayload IS valid JSON array)
         AND system.hasNoExportEndpoint()
         AND system.hasNoImportEndpoint()
END FUNCTION
```

### Examples

- 用户选中 3 个实例点击"导出" → 期望：下载 JSON 文件 → 实际：没有导出按钮和 API
- 用户拖入一个包含 5 个实例配置的 JSON 文件 → 期望：预览并批量导入 → 实际：没有导入功能
- 用户导出时选择不包含 API Key → 期望：JSON 中 api_key 字段为空字符串或不存在 → 实际：无法操作
- 用户导入的 JSON 中有一个与现有实例同名 → 期望：提示冲突并提供策略选择 → 实际：无法操作

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- 通过"新建实例"按钮手动创建单个实例的完整流程（POST /api/instances，201 响应）
- 编辑和删除已有实例的正常操作（PUT/DELETE /api/instances/{id}）
- 实例列表查看和详情展示（含脱敏 api_key 和用量统计）
- 按类型筛选实例列表的过滤逻辑
- 批量选择后执行删除操作
- 多租户隔离（created_by 和 resource:read:all 权限检查）

**Scope:**
所有不涉及导入/导出操作的请求应完全不受影响。这包括：
- GET /api/instances（列表和筛选）
- POST /api/instances（单个创建）
- GET/PUT/DELETE /api/instances/{id}（单个查看/更新/删除）
- 前端的视图切换（卡片/列表）、全选/单选逻辑

## Hypothesized Root Cause

这是一个功能缺失型问题（非代码缺陷），根因如下：

1. **后端缺少导出端点**: `instances.py` 路由中没有 `/export` 端点，无法接收实例 ID 列表并返回包含配置数据的 JSON 响应

2. **后端缺少导入端点**: `instances.py` 路由中没有 `/import` 端点，无法接收 JSON 数组并批量创建/更新实例

3. **InstanceService 缺少批量操作方法**: 服务层只有单个实例的 CRUD 方法，没有批量导出（含/不含 api_key）和批量导入（含冲突处理）的逻辑

4. **前端缺少 UI 入口和交互组件**: InstancesPage 只有"新建实例"按钮和批量删除，没有导入/导出按钮、导出选项对话框和导入预览对话框

5. **缺少导入/导出相关的 Pydantic 模型**: 后端没有定义导出请求体（instance_ids + include_api_key）和导入请求体（instances 数组 + conflict_strategy）的数据模型

## Correctness Properties

Property 1: Bug Condition - 导入/导出功能可用

_For any_ 用户操作 where 用户选中至少一个实例并触发导出、或上传有效 JSON 文件触发导入（isBugCondition returns true），修复后的系统 SHALL 提供完整的导入/导出流程：导出返回符合预期的 JSON 数据（根据 include_api_key 选项决定是否包含 api_key），导入正确解析 JSON 并按冲突策略批量创建或更新实例。

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7**

Property 2: Preservation - 现有 CRUD 和列表功能不变

_For any_ 用户操作 where 操作不涉及导入/导出（isBugCondition returns false），修复后的系统 SHALL 产生与修复前完全相同的行为，保持单实例创建/编辑/删除、列表筛选、批量删除、脱敏展示和多租户隔离的正确性。

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

假设我们的根因分析正确：

**File**: `backend/app/models/instance.py`

**新增模型**:
1. **ExportRequest**: 导出请求体模型
   - `instance_ids: list[str]` — 要导出的实例 ID 列表
   - `include_api_key: bool = False` — 是否包含明文 API Key

2. **ImportInstanceItem**: 单个导入实例条目
   - `name: str` — 必填
   - `endpoint: str` — 必填
   - `api_key: str = ""` — 可选（未含时前端需补填）
   - `deployment: str` — 必填
   - `type: InstanceType` — 必填
   - `description: str = ""` — 可选

3. **ImportRequest**: 导入请求体模型
   - `instances: list[ImportInstanceItem]` — 要导入的实例列表
   - `conflict_strategy: Literal["skip", "update"] = "skip"` — 冲突策略

4. **ImportResult**: 导入结果响应模型
   - `created: int` — 新创建数量
   - `updated: int` — 覆盖更新数量
   - `skipped: int` — 跳过数量
   - `errors: list[str]` — 错误信息列表

---

**File**: `backend/app/services/instance_service.py`

**Function**: `export_instances` 和 `import_instances`

**Specific Changes**:
1. **新增 export_instances 方法**: 接收 instance_ids 和 include_api_key，查询匹配的实例数据，根据 include_api_key 决定是否包含 api_key 字段，返回实例配置列表。需检查多租户权限（只能导出自己的实例，除非有 resource:read:all）。

2. **新增 import_instances 方法**: 接收实例列表和冲突策略，逐条校验必填字段（name, endpoint, deployment, type），对于每条记录：
   - 检查 name 是否已存在
   - 若存在且策略为 "skip"：跳过
   - 若存在且策略为 "update"：执行 UPDATE
   - 若不存在：执行 INSERT
   - 记录 created_by = user.id
   - 收集错误信息（字段缺失/类型无效等）

3. **事务处理**: 整个导入操作在一个数据库事务中执行，任何单条记录的校验错误不中止其他记录的处理（部分成功模式），最终返回 ImportResult 统计。

---

**File**: `backend/app/api/instances.py`

**新增路由**:
1. **POST /api/instances/export**: 需要 `instance:read` 权限，调用 service.export_instances，返回实例配置 JSON 数组
2. **POST /api/instances/import**: 需要 `instance:write` 权限，调用 service.import_instances，返回 ImportResult

---

**File**: `frontend/src/pages/InstancesPage.tsx`

**UI Changes**:
1. **Header 区域添加导入/导出按钮**: 在"新建实例"按钮旁增加"导入"和"导出"按钮（使用 Upload 和 Download 图标）
2. **导出按钮联动已选实例**: 当有选中实例时，导出按钮可点击，触发导出对话框
3. **导出对话框组件**: 展示选中实例列表（可勾选/取消），提供"包含 API Key"开关，确认后调用 export API 并用 Blob 下载
4. **导入按钮打开文件选择器**: 点击导入按钮触发 `<input type="file" accept=".json">` 选择 JSON 文件
5. **导入预览对话框组件**: 解析 JSON 后展示预览表格（name, type, endpoint），可勾选要导入的条目，缺失 api_key 时显示输入框要求补填，提供冲突策略选择（跳过/更新），确认后调用 import API 并展示结果

---

**File**: `frontend/src/components/instances/ExportDialog.tsx`（新建）

**组件职责**:
- Props: `open`, `onClose`, `instances`（已选实例列表）
- 展示实例勾选列表（默认全选）
- "包含 API Key" Switch 开关
- 确认导出按钮 → 调用 POST /api/instances/export → Blob 下载为 `instances-export-{date}.json`

---

**File**: `frontend/src/components/instances/ImportDialog.tsx`（新建）

**组件职责**:
- Props: `open`, `onClose`, `onSuccess`
- 步骤 1: 文件选择和解析，校验 JSON 格式
- 步骤 2: 预览表格展示解析结果，勾选要导入的条目（默认全选）
- 步骤 3: 缺失 api_key 的条目显示输入框要求补填
- 冲突策略选择（RadioGroup: 跳过 / 更新）
- 确认导入按钮 → 调用 POST /api/instances/import → 展示结果摘要（created/updated/skipped/errors）

## Testing Strategy

### Validation Approach

测试策略分两阶段：首先通过探索性测试确认 bug 存在（功能缺失），然后验证修复后导入/导出正常工作且不破坏现有功能。

### Exploratory Bug Condition Checking

**Goal**: 在实现修复前，确认当前系统确实缺少导入/导出端点，以验证根因分析的正确性。

**Test Plan**: 直接调用预期的 API 端点，确认返回 404/405，证明功能不存在。

**Test Cases**:
1. **Export Endpoint Missing**: POST /api/instances/export → 期望返回 404 或 405（will fail on unfixed code）
2. **Import Endpoint Missing**: POST /api/instances/import → 期望返回 404 或 405（will fail on unfixed code）
3. **UI Entry Missing**: 检查 InstancesPage 渲染结果，确认没有"导入"/"导出"按钮

**Expected Counterexamples**:
- 调用 export/import 端点返回 Method Not Allowed 或 Not Found
- 前端页面无导入导出相关 UI 元素

### Fix Checking

**Goal**: 验证对于所有满足 bug condition 的输入，修复后的系统产生期望行为。

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  IF input.action == "export" THEN
    result := POST /api/instances/export(input.instance_ids, input.include_api_key)
    ASSERT result.status == 200
    ASSERT result.body is valid JSON array
    ASSERT each item contains required fields (name, endpoint, deployment, type)
    IF input.include_api_key THEN
      ASSERT each item contains api_key (plaintext)
    ELSE
      ASSERT no item contains api_key OR api_key == ""
    END IF
  END IF

  IF input.action == "import" THEN
    result := POST /api/instances/import(input.instances, input.conflict_strategy)
    ASSERT result.status == 200
    ASSERT result.body contains created, updated, skipped, errors counts
    ASSERT sum(created + updated + skipped) == len(input.instances)
    FOR each instance WHERE name conflicts AND strategy == "skip" DO
      ASSERT instance NOT updated in DB
    END FOR
    FOR each instance WHERE name conflicts AND strategy == "update" DO
      ASSERT instance IS updated in DB with new values
    END FOR
  END IF
END FOR
```

### Preservation Checking

**Goal**: 验证对于所有不涉及导入/导出的操作，修复后的系统行为与修复前完全一致。

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalSystem(input) = fixedSystem(input)
END FOR
```

**Testing Approach**: 属性测试（PBT）适合验证保持性，因为：
- 它能自动生成大量测试用例覆盖各种输入组合
- 能捕获手动测试可能遗漏的边界情况
- 提供对非 bug 输入行为不变的强保证

**Test Plan**: 在未修复代码上观察现有 CRUD 操作的行为，然后编写属性测试确保修复后行为一致。

**Test Cases**:
1. **Single Create Preservation**: 验证单个实例创建（POST /api/instances）在修复后仍正常返回 201，且数据正确入库
2. **List & Filter Preservation**: 验证列表查询和类型筛选逻辑不受影响
3. **Update Preservation**: 验证实例编辑（PUT /api/instances/{id}）在修复后行为一致
4. **Delete Preservation**: 验证实例删除（DELETE /api/instances/{id}）在修复后行为一致，含活跃会话拒绝删除
5. **Multi-tenant Preservation**: 验证多租户隔离规则不受影响

### Unit Tests

- 测试 export_instances 方法：正常导出、include_api_key=True/False、空 instance_ids、无效 ID
- 测试 import_instances 方法：正常导入、冲突跳过、冲突更新、字段缺失校验、类型无效校验
- 测试导入时 api_key 为空的处理逻辑
- 测试多租户权限：用户只能导出自己的实例
- 测试导出结果的 JSON 结构符合预期 schema

### Property-Based Tests

- 生成随机实例配置列表，验证导出后再导入能完整还原（round-trip 属性）
- 生成随机冲突场景（已有同名实例），验证 skip 策略不修改数据、update 策略正确覆盖
- 生成随机非导入/导出操作序列，验证修复前后行为一致
- 生成各种 JSON 格式（含非法字段、缺失字段、额外字段），验证校验逻辑健壮性

### Integration Tests

- 完整流程：创建实例 → 导出 → 删除实例 → 导入 → 验证恢复
- 跨用户隔离：用户 A 导出的配置，用户 B 导入后 created_by 为 B
- 大批量导入/导出（50+ 实例）的性能和正确性
- 前端完整交互流程：选择实例 → 点击导出 → 确认 → 下载文件 → 点击导入 → 选择文件 → 预览 → 确认 → 查看结果
- 导入含冲突实例时 UI 正确展示冲突策略选项并按选择执行
