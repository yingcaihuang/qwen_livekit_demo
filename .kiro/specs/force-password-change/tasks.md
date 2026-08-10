# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Local User Force Password Change Bypass
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to concrete failing cases: local user with `must_change_password=true` calling `/api/auth/me` and navigating protected routes
  - **Backend (pytest)**: Create test in `azure-voice-admin/backend/tests/test_force_password_bug.py`
    - Set up a local user with `auth_source='local'` and `must_change_password=true` in the test database
    - Call `GET /api/auth/me` with the user's session
    - Assert `response.json()["must_change_password"] == True` (will FAIL - endpoint returns `false`)
    - Assert `"auth_source" in response.json()` and `response.json()["auth_source"] == "local"` (will FAIL - field missing)
  - **Frontend (vitest)**: Create test in `azure-voice-admin/frontend/src/components/auth/__tests__/ProtectedRoute.bug.test.tsx`
    - Render `ProtectedRoute` with user context where `must_change_password=true` and `auth_source='local'`
    - Assert that navigation redirects to `/change-password` (will FAIL - no redirect logic exists)
    - Render `Sidebar` with SSO user context
    - Assert that `KeyRound` icon is NOT rendered (will FAIL - icon always shown)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct - it proves the bug exists)
  - Document counterexamples found:
    - `/api/auth/me` returns `must_change_password: false` for user with DB value `true` (MeResponse default)
    - `/api/auth/me` has no `auth_source` field in response
    - `ProtectedRoute` renders children without redirect for `must_change_password=true` user
    - `Sidebar` shows `KeyRound` for SSO users
  - Mark task complete when tests are written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Force-Change Users Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - **Backend (pytest)**: Create test in `azure-voice-admin/backend/tests/test_force_password_preservation.py`
    - Observe: local user with `must_change_password=false` calling `/api/auth/me` returns user info with `must_change_password=false` on unfixed code
    - Observe: SSO user calling `/api/auth/me` returns user info normally on unfixed code
    - Observe: unauthenticated request to `/api/auth/me` returns 401 on unfixed code
    - Write property-based test (using `hypothesis`): for all users where NOT (`auth_source='local' AND must_change_password=true`), the `/api/auth/me` response fields (id, username, roles, capabilities) remain unchanged
    - Verify tests pass on UNFIXED code
  - **Frontend (vitest)**: Create test in `azure-voice-admin/frontend/src/components/auth/__tests__/ProtectedRoute.preservation.test.tsx`
    - Observe: `ProtectedRoute` with `must_change_password=false` local user renders children normally
    - Observe: `ProtectedRoute` with SSO user renders children normally
    - Observe: `ProtectedRoute` without user redirects to `/login`
    - Observe: `ProtectedRoute` with capability check and user lacking capability redirects to `/`
    - Observe: `Sidebar` with `auth_source='local'` and `must_change_password=false` user shows `KeyRound` icon
    - Write property-based tests covering all non-bug-condition user configurations
    - Verify tests pass on UNFIXED code
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 3. Fix for local user force password change bypass

  - [x] 3.1 Extend `CurrentUser` dataclass and `get_current_user()` query in `deps.py`
    - Add `must_change_password: bool` field to `CurrentUser` dataclass
    - Add `auth_source: str` field to `CurrentUser` dataclass
    - Modify SQL query in `get_current_user()` from `SELECT id, username, is_active` to `SELECT id, username, is_active, must_change_password, auth_source`
    - Assign queried values to the new `CurrentUser` fields
    - Update `_get_test_user()` to include `must_change_password=False` and `auth_source='local'` for test compatibility
    - _Bug_Condition: isBugCondition(input) where input.user.auth_source='local' AND input.user.must_change_password=true_
    - _Expected_Behavior: CurrentUser accurately reflects DB state for must_change_password and auth_source_
    - _Preservation: Existing CurrentUser fields (id, username, roles, capabilities) unchanged_
    - _Requirements: 2.1, 2.2_

  - [x] 3.2 Modify `MeResponse` and `me()` endpoint in `auth.py`
    - Add `auth_source: str` field to `MeResponse` model
    - Update `me()` function to pass `user.must_change_password` and `user.auth_source` to `MeResponse`
    - Remove reliance on default value `False` for `must_change_password` — use actual value from `CurrentUser`
    - _Bug_Condition: isBugCondition(input) where me() previously returned must_change_password=false regardless of DB value_
    - _Expected_Behavior: me() returns accurate must_change_password and auth_source from CurrentUser_
    - _Preservation: All other MeResponse fields (id, username, roles, capabilities) remain unchanged_
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 Extend `AuthUser` interface and `fetchMe` in `AuthProvider.tsx`
    - Add `auth_source?: string` to `AuthUser` interface
    - Update `fetchMe` to extract `auth_source` from `/api/auth/me` response and store in user state
    - Ensure `must_change_password` (already present) and `auth_source` are propagated through context
    - _Bug_Condition: Frontend user state lacked auth_source, preventing route guard from distinguishing local vs SSO_
    - _Expected_Behavior: AuthUser contains auth_source from me() response_
    - _Preservation: Existing AuthUser fields and logout/refreshAuth behavior unchanged_
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 3.4 Add force password change redirect in `ProtectedRoute.tsx`
    - After `if (!user)` check and before capability check, add condition:
      `if (user.must_change_password && user.auth_source === 'local')` → `return <Navigate to="/change-password" replace />`
    - This ensures local users with `must_change_password=true` are redirected before accessing any protected route
    - SSO users bypass this check (their `auth_source` is not `'local'`)
    - _Bug_Condition: isBugCondition(input) where ProtectedRoute previously had no must_change_password check_
    - _Expected_Behavior: Navigate to /change-password for all inputs satisfying bug condition_
    - _Preservation: Non-bug-condition users (SSO, local with must_change_password=false) pass through unchanged_
    - _Requirements: 2.3, 2.4, 3.1, 3.2_

  - [x] 3.5 Conditionally render change-password entry in `Sidebar.tsx`
    - Wrap the `KeyRound` link with condition: only render when `user.auth_source === 'local'`
    - Access `auth_source` from `user` object via `useAuth()`
    - SSO users will no longer see the change-password icon
    - _Bug_Condition: Sidebar showed KeyRound for all users including SSO who cannot change local passwords_
    - _Expected_Behavior: KeyRound hidden for SSO users, visible for local users_
    - _Preservation: Local users with must_change_password=false still see KeyRound icon (voluntary password change)_
    - _Requirements: 2.5, 3.4_

  - [x] 3.6 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Local User Force Password Change Enforcement
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.7 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Force-Change Users Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full backend test suite: `cd azure-voice-admin/backend && pytest`
  - Run full frontend test suite: `cd azure-voice-admin/frontend && npx vitest --run`
  - Ensure all tests pass, ask the user if questions arise.
