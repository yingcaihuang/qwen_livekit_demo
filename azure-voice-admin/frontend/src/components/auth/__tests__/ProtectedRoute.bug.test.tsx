/**
 * Bug condition exploration test: Local User Force Password Change Bypass.
 *
 * **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
 *
 * Property 1: Bug Condition — Local User Force Password Change Bypass
 *
 * CRITICAL: This test MUST FAIL on unfixed code — failure confirms the bug exists.
 * DO NOT fix the test or the code when it fails.
 *
 * Goal: Surface counterexamples that demonstrate:
 * - ProtectedRoute does not redirect local users with must_change_password=true to /change-password
 * - Sidebar shows KeyRound icon for SSO users (who cannot change local passwords)
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

// Mock useAuth to inject controlled auth state
vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: vi.fn(),
}))

import { useAuth } from '@/components/auth/AuthProvider'
import { ProtectedRoute } from '../ProtectedRoute'
import { Sidebar } from '@/components/layout/Sidebar'

const mockedUseAuth = vi.mocked(useAuth)

describe('Bug Condition: ProtectedRoute force password change redirect', () => {
  it('EXPECTED TO FAIL: should redirect local user with must_change_password=true to /change-password', () => {
    /**
     * COUNTEREXAMPLE: ProtectedRoute renders children for a local user with
     * must_change_password=true instead of redirecting to /change-password.
     *
     * Root cause: ProtectedRoute has no logic to check must_change_password
     * or auth_source fields.
     */
    mockedUseAuth.mockReturnValue({
      user: { id: 'user-1', username: 'admin', must_change_password: true, auth_source: 'local' },
      roles: ['operator'],
      capabilities: ['dashboard:read'],
      loading: false,
      csrfToken: 'csrf-token',
      logout: vi.fn(),
      refreshAuth: vi.fn(),
    })

    let currentPath = ''
    function LocationDisplay() {
      // We use this to capture where we ended up
      return null
    }

    const { container } = render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <div data-testid="protected-content">Dashboard Content</div>
              </ProtectedRoute>
            }
          />
          <Route path="/change-password" element={<div data-testid="change-password-page">Change Password</div>} />
        </Routes>
      </MemoryRouter>
    )

    // Bug: ProtectedRoute does NOT redirect to /change-password
    // It renders children normally, so protected-content is visible
    // Expected: should redirect, so protected-content should NOT be in the document
    // and change-password-page SHOULD be rendered
    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument()
    expect(screen.getByTestId('change-password-page')).toBeInTheDocument()
  })

  it('EXPECTED TO FAIL: should NOT redirect SSO user even if must_change_password is true', () => {
    /**
     * This test verifies the boundary: SSO users should NOT be redirected
     * even if must_change_password is somehow true.
     * On unfixed code, no redirect logic exists at all, so this may pass vacuously.
     * But it documents the expected behavior for the fix.
     */
    mockedUseAuth.mockReturnValue({
      user: { id: 'user-2', username: 'sso_user', must_change_password: true, auth_source: 'sso' },
      roles: ['operator'],
      capabilities: ['dashboard:read'],
      loading: false,
      csrfToken: 'csrf-token',
      logout: vi.fn(),
      refreshAuth: vi.fn(),
    })

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <div data-testid="protected-content">Dashboard Content</div>
              </ProtectedRoute>
            }
          />
          <Route path="/change-password" element={<div data-testid="change-password-page">Change Password</div>} />
        </Routes>
      </MemoryRouter>
    )

    // SSO users should NOT be redirected — they should see protected content
    expect(screen.getByTestId('protected-content')).toBeInTheDocument()
  })
})

describe('Bug Condition: Sidebar KeyRound visibility for SSO users', () => {
  it('EXPECTED TO FAIL: should NOT show KeyRound change-password icon for SSO users', () => {
    /**
     * COUNTEREXAMPLE: Sidebar renders the KeyRound (change-password) link for
     * SSO users who cannot change local passwords.
     *
     * Root cause: Sidebar always renders KeyRound without checking auth_source.
     */
    mockedUseAuth.mockReturnValue({
      user: { id: 'user-sso', username: 'sso_user', must_change_password: false, auth_source: 'sso' },
      roles: ['operator'],
      capabilities: ['dashboard:read', 'instance:read'],
      loading: false,
      csrfToken: 'csrf-token',
      logout: vi.fn(),
      refreshAuth: vi.fn(),
    })

    render(
      <MemoryRouter initialEntries={['/']}>
        <Sidebar />
      </MemoryRouter>
    )

    // Bug: Sidebar shows the change-password link (KeyRound icon) for ALL users
    // including SSO users who cannot change local passwords
    // Expected: No link to /change-password for SSO users
    const changePasswordLink = screen.queryByTitle('修改密码')
    expect(changePasswordLink).not.toBeInTheDocument()
  })
})
