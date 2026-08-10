# Force Password Change Bugfix Design

## Overview

本地账号首次登录强制改密码功能因后端 `/api/auth/me` 未返回 `must_change_password` 和 `auth_source` 字段、前端路由守卫未拦截需改密用户而失效。修复策略为：后端 `me` 端点补充缺失字段查询和返回，前端 `ProtectedRoute` 增加强制改密码跳转逻辑，`Sidebar` 根据 `auth_source` 条件渲染改密码入口。修复范围最小化，仅修改数据流路径上的必要组件。

## Glossary

- **Bug_Condition (C)**: 用户为本地账号（`auth_source='local'`）且 `must_change_password=true` 时触发的强制改密码条件
- **Property (P)**: 满足 Bug Condition 时，用户在访问任何非 `/change-password` 的受保护路由时应被重定向到 `/change-password`
- **Preservation**: 非本地用户（SSO）和 `must_change_password=false` 的本地用户的既有行为不受影响
- **`me()` endpoint**: `backend/app/api/auth.py` 中的 `/api/auth/me` 路由，返回当前认证用户信息
- **`CurrentUser`**: `backend/app/api/deps.py` 中的数据类，表示从 session 中解析的当前用户
- **`ProtectedRoute`**: `frontend/src/components/auth/ProtectedRoute.tsx` 中的路由守卫组件
- **`AuthProvider`**: `frontend/src/components/auth/AuthProvider.tsx` 中的认证状态管理组件

## Bug Details

### Bug Condition

当本地账号用户（`auth_source='local'`）的 `must_change_password` 标记为 `true` 时，`/api/auth/me` 端点未从数据库查询该字段，导致前端无法得知用户需要改密码，`ProtectedRoute` 也未对此做拦截处理。

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type AuthenticatedRequest
  OUTPUT: boolean

  RETURN input.user.auth_source = 'local'
         AND input.user.must_change_password = true
         AND input.targetRoute ≠ '/change-password'
         AND userCanAccessProtectedRoute(input.user)
END FUNCTION
```

### Examples

- 用户 `admin`（本地账号，`must_change_password=true`）登录后访问 `/instances`，期望被重定向到 `/change-password`，实际可正常访问 `/instances`
- 用户 `admin`（本地账号，`must_change_password=true`）在 Dashboard 页面刷新浏览器，期望刷新后重定向到 `/change-password`，实际停留在 Dashboard
- 用户 `admin`（本地账号，`must_change_password=true`）调用 `GET /api/auth/me`，期望返回 `{ must_change_password: true, auth_source: "local" }`，实际返回 `{ must_change_password: false }` 且无 `auth_source` 字段
- SSO 用户 `sso_user` 登录后访问任意路由，期望正常访问（不受此逻辑影响），实际正常访问（此场景无 bug）

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- 本地用户 `must_change_password=false` 时正常访问所有受保护路由，基于 capability 检查
- SSO 用户无论 `must_change_password` 值如何，均正常访问受保护路由
- `/api/auth/change-password` 成功后清除 `must_change_password` 标记并允许正常访问
- 未认证用户访问受保护路由仍重定向到 `/login`
- `ProtectedRoute` 的 capability 检查逻辑不变
- `/api/auth/login` 响应中仍正确返回 `must_change_password`
- 鼠标点击按钮进行退出登录等操作不受影响

**Scope:**
所有不满足 `auth_source='local' AND must_change_password=true` 条件的请求/导航不受此修复影响。包括：
- SSO 用户的所有操作
- 本地用户 `must_change_password=false` 的所有操作
- 未认证用户的路由跳转
- `/change-password` 页面本身的访问

## Hypothesized Root Cause

Based on the bug description, the most likely issues are:

1. **`me()` 端点未查询关键字段**: `auth.py` 中的 `me()` 函数直接使用 `CurrentUser` dataclass 返回响应，但 `CurrentUser` 不含 `must_change_password` 和 `auth_source` 字段，`me()` 也未额外查询数据库获取这些字段
   - `CurrentUser` dataclass 仅有 `id`, `username`, `roles`, `capabilities`
   - `get_current_user()` 依赖函数查询了 `id, username, is_active` 但未查询 `must_change_password` 和 `auth_source`
   - `MeResponse` model 的 `must_change_password` 默认值为 `False`，永远返回 false

2. **前端 `ProtectedRoute` 缺少强制改密码逻辑**: 组件仅检查 `user` 是否存在和 `capability` 权限，未检查 `must_change_password` 状态

3. **前端 `AuthProvider` 未传播 `auth_source`**: `AuthUser` 接口未包含 `auth_source` 字段，`fetchMe` 未存储此字段

4. **Sidebar 无条件显示改密码入口**: 未根据 `auth_source` 过滤，SSO 用户也看到改密码图标

## Correctness Properties

Property 1: Bug Condition - 本地用户强制改密码重定向

_For any_ authenticated request where the user is a local account (`auth_source='local'`) with `must_change_password=true`, navigating to any protected route other than `/change-password` SHALL redirect the user to `/change-password` and prevent access to the requested page. Additionally, `GET /api/auth/me` SHALL return `must_change_password: true` and `auth_source: "local"` accurately.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation - 非强制改密码用户行为不变

_For any_ authenticated request where the user is either (a) an SSO user regardless of `must_change_password` value, or (b) a local user with `must_change_password=false`, the fixed code SHALL produce exactly the same routing and access behavior as the original code, preserving normal capability-based access control and sidebar display logic.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `azure-voice-admin/backend/app/api/deps.py`

**Changes**:
1. **扩展 `CurrentUser` dataclass**: 添加 `must_change_password: bool` 和 `auth_source: str` 字段
2. **修改 `get_current_user()` 查询**: SELECT 语句增加 `must_change_password` 和 `auth_source` 列，赋值到 `CurrentUser`

---

**File**: `azure-voice-admin/backend/app/api/auth.py`

**Function**: `me()`

**Changes**:
3. **修改 `MeResponse` model**: 添加 `auth_source: str` 字段
4. **修改 `me()` 返回值**: 从 `CurrentUser` 对象读取 `must_change_password` 和 `auth_source` 并返回（无需额外数据库查询，因为 `get_current_user` 已查询）

---

**File**: `azure-voice-admin/frontend/src/components/auth/AuthProvider.tsx`

**Changes**:
5. **扩展 `AuthUser` 接口**: 添加 `auth_source?: string` 字段
6. **修改 `fetchMe` 函数**: 从 `/api/auth/me` 响应中提取 `auth_source` 并存储到 user 状态

---

**File**: `azure-voice-admin/frontend/src/components/auth/ProtectedRoute.tsx`

**Changes**:
7. **添加强制改密码重定向逻辑**: 在认证通过后、capability 检查前，检查 `user.must_change_password === true && user.auth_source === 'local'`，若满足则重定向到 `/change-password`（当前路由为 `/change-password` 时不重定向以避免死循环 — 但该路由为公开路由不经过 ProtectedRoute，无此问题）

---

**File**: `azure-voice-admin/frontend/src/components/layout/Sidebar.tsx`

**Changes**:
8. **条件渲染改密码入口**: 获取 `user.auth_source`，仅当 `auth_source === 'local'` 时显示 `KeyRound` 改密码图标链接

## Testing Strategy

### Validation Approach

测试策略分两阶段：首先在未修复代码上编写探索性测试验证 bug 确实存在并确认根因，然后在修复后运行 fix checking 和 preservation checking 验证修复正确且无回归。

### Exploratory Bug Condition Checking

**Goal**: 在未修复代码上验证 bug 确实存在，确认或推翻根因假设。若推翻则需重新假设。

**Test Plan**: 编写后端测试模拟本地用户（`must_change_password=true`）调用 `/api/auth/me`，验证响应中缺少正确的字段值。编写前端测试验证 `ProtectedRoute` 不拦截需改密码用户。在未修复代码上运行观察失败。

**Test Cases**:
1. **me 端点缺失字段测试**: 调用 `/api/auth/me`（本地用户，`must_change_password=true`），断言 `must_change_password` 为 `true` — 未修复代码将返回 `false`（失败）
2. **me 端点缺失 auth_source 测试**: 调用 `/api/auth/me`，断言响应包含 `auth_source` 字段 — 未修复代码无此字段（失败）
3. **ProtectedRoute 未拦截测试**: 渲染 `ProtectedRoute`（用户 `must_change_password=true`），断言重定向到 `/change-password` — 未修复代码无重定向（失败）
4. **Sidebar SSO 用户显示测试**: 渲染 `Sidebar`（SSO 用户），断言不显示改密码图标 — 未修复代码显示图标（失败）

**Expected Counterexamples**:
- `/api/auth/me` 对 `must_change_password=true` 的用户返回 `must_change_password: false`
- Possible causes: `MeResponse` 默认值为 `False`，`me()` 未从 DB 查询该字段，`CurrentUser` 不含该字段

### Fix Checking

**Goal**: 验证对所有满足 bug condition 的输入，修复后的函数产生期望行为。

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  meResponse := GET /api/auth/me(input.session)
  ASSERT meResponse.must_change_password = true
  ASSERT meResponse.auth_source = 'local'

  routeResult := ProtectedRoute.render(user=input.user, targetRoute=input.route)
  ASSERT routeResult.redirectsTo = '/change-password'
END FOR
```

### Preservation Checking

**Goal**: 验证对所有不满足 bug condition 的输入，修复后的函数产生与原函数相同的结果。

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT me_original(input) = me_fixed(input)  // 非 must_change_password 用户响应不变
  ASSERT ProtectedRoute_original(input) = ProtectedRoute_fixed(input)  // 路由行为不变
  ASSERT Sidebar_original(input) = Sidebar_fixed(input)  // Sidebar 显示不变（本地用户仍显示）
END FOR
```

**Testing Approach**: 建议使用 property-based testing 进行 preservation checking，因为：
- 可自动生成大量测试用例覆盖输入域
- 能捕获手动单元测试可能遗漏的边界情况
- 提供强保证：所有非 buggy 输入的行为不变

**Test Plan**: 先在未修复代码上观察 SSO 用户和 `must_change_password=false` 本地用户的行为（应正常），然后编写 property-based tests 捕获该行为作为基线。

**Test Cases**:
1. **SSO 用户路由保留**: 验证 SSO 用户访问所有受保护路由时行为与修复前一致
2. **本地用户正常访问保留**: 验证 `must_change_password=false` 的本地用户访问路由时行为不变
3. **Capability 检查保留**: 验证缺少 capability 的用户仍被重定向到 `/`
4. **未认证用户保留**: 验证未登录用户仍被重定向到 `/login`
5. **Sidebar 本地用户显示保留**: 验证 `auth_source='local'` 用户仍看到改密码图标

### Unit Tests

- 后端：测试 `get_current_user()` 返回的 `CurrentUser` 包含 `must_change_password` 和 `auth_source`
- 后端：测试 `me()` 端点对不同用户类型返回正确的 `must_change_password` 和 `auth_source`
- 前端：测试 `ProtectedRoute` 对 `must_change_password=true` 且 `auth_source='local'` 的用户重定向
- 前端：测试 `ProtectedRoute` 对 SSO 用户和正常本地用户不重定向
- 前端：测试 `Sidebar` 对 SSO 用户不渲染改密码入口

### Property-Based Tests

- 生成随机用户配置（auth_source × must_change_password × capabilities）验证路由守卫行为正确性
- 生成随机 SSO/local 用户组合验证 Sidebar 显示逻辑一致性
- 生成多种 `must_change_password` 状态组合验证 `/api/auth/me` 返回值准确性

### Integration Tests

- 端到端测试：本地用户 `must_change_password=true` 登录后被重定向到改密码页面，改密码成功后可正常访问 Dashboard
- 端到端测试：SSO 用户登录后直接访问 Dashboard，不受任何改密码逻辑影响
- 端到端测试：本地用户在 Dashboard 刷新页面后仍被重定向到改密码页面（验证 `refreshAuth` 正确传递字段）
