# Bugfix Requirements Document

## Introduction

本地账号（`auth_source='local'`）的首次登录强制改密码功能未正确工作。系统已有 `must_change_password` 数据库字段、改密码 API 和前端页面，但由于后端 `/api/auth/me` 未返回关键字段、前端路由守卫未拦截需改密用户、以及页面刷新后强制状态丢失，导致本地用户可以绕过首次改密码要求继续使用系统。此 bug 仅影响 `auth_source='local'` 的用户；SSO（OIDC/SAML）用户不受影响。

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a local user with `must_change_password=true` calls `/api/auth/me` THEN the system returns `must_change_password` as its default value `false` because the `me()` endpoint does not query the `must_change_password` field from the database nor include it in the response

1.2 WHEN a local user with `must_change_password=true` calls `/api/auth/me` THEN the system does not return the `auth_source` field, preventing the frontend from distinguishing local vs SSO users

1.3 WHEN a local user with `must_change_password=true` navigates to any protected route (e.g. Dashboard, Instances) THEN the `ProtectedRoute` component allows access without redirecting to `/change-password`

1.4 WHEN a local user with `must_change_password=true` logs in successfully and the page is subsequently refreshed THEN the system loses the forced redirect state because `refreshAuth()` via `/api/auth/me` returns incorrect `must_change_password` value, allowing the user to use the system without changing their password

1.5 WHEN an SSO user is authenticated THEN the sidebar displays the change-password icon (`KeyRound`), even though SSO users cannot change local passwords

### Expected Behavior (Correct)

2.1 WHEN a local user with `must_change_password=true` calls `/api/auth/me` THEN the system SHALL query the `must_change_password` and `auth_source` fields from the database and return them accurately in the response

2.2 WHEN a local user with `must_change_password=true` calls `/api/auth/me` THEN the system SHALL return `auth_source` field value (e.g. `"local"`, `"sso"`) so the frontend can distinguish user types

2.3 WHEN a local user with `must_change_password=true` navigates to any protected route other than `/change-password` THEN the system SHALL redirect the user to `/change-password` and prevent access to the requested page

2.4 WHEN a local user with `must_change_password=true` refreshes the page on any protected route THEN the system SHALL re-fetch `/api/auth/me`, detect `must_change_password=true`, and redirect to `/change-password`

2.5 WHEN an SSO user is authenticated THEN the sidebar SHALL NOT display the change-password entry (KeyRound icon), since SSO users do not have local passwords to change

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a local user with `must_change_password=false` navigates to any protected route THEN the system SHALL CONTINUE TO allow access normally based on capability checks

3.2 WHEN an SSO user navigates to any protected route THEN the system SHALL CONTINUE TO allow access normally without any must_change_password enforcement regardless of the field value

3.3 WHEN a local user successfully changes their password via `/api/auth/change-password` THEN the system SHALL CONTINUE TO clear the `must_change_password` flag and allow normal access

3.4 WHEN a local user with `must_change_password=false` is authenticated THEN the sidebar SHALL CONTINUE TO display the change-password entry so the user can voluntarily change their password

3.5 WHEN a user is not authenticated and navigates to a protected route THEN the system SHALL CONTINUE TO redirect to `/login`

3.6 WHEN the login API `/api/auth/login` is called with valid credentials THEN the system SHALL CONTINUE TO return `must_change_password` in the login response and redirect accordingly

3.7 WHEN `ProtectedRoute` receives a `capability` prop and the user lacks that capability THEN the system SHALL CONTINUE TO redirect to `/` as before

---

## Bug Condition (Formal)

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type AuthenticatedRequest
  OUTPUT: boolean

  // Returns true when the user is a local account that must change password
  RETURN X.user.auth_source = 'local' AND X.user.must_change_password = true
END FUNCTION
```

```pascal
// Property: Fix Checking - Force password change for local users
FOR ALL X WHERE isBugCondition(X) DO
  meResponse ← GET /api/auth/me
  ASSERT meResponse.must_change_password = true
  ASSERT meResponse.auth_source = 'local'

  routeAccess ← navigate(X, anyProtectedRoute ≠ '/change-password')
  ASSERT routeAccess.redirectedTo = '/change-password'
END FOR
```

```pascal
// Property: Preservation Checking
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
  // i.e., non-local users and local users with must_change_password=false
  // behave identically before and after the fix
END FOR
```
