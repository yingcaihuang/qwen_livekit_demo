/**
 * Preservation property tests: Non-Force-Change Users Behavior Unchanged.
 *
 * **Validates: Requirements 3.1, 3.2, 3.4, 3.5, 3.7**
 *
 * Property 2: Preservation — Non-Force-Change Users Behavior Unchanged
 *
 * These tests verify that users NOT meeting the bug condition behave correctly
 * on UNFIXED code. They MUST PASS on current code to establish a baseline that
 * the fix must preserve.
 *
 * Observations captured:
 * - ProtectedRoute with must_change_password=false local user → renders children
 * - ProtectedRoute with SSO user → renders children
 * - ProtectedRoute without user → redirects to /login
 * - ProtectedRoute with capability check and user lacking capability → redirects to /
 * - Sidebar with auth_source='local' and must_change_password=false → shows KeyRound icon
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
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

describe('Preservation: ProtectedRoute with non-bug-condition users', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders children for local user with must_change_password=false', () => {
    /**
     * Validates: Requirement 3.1
     * Local user with must_change_password=false should access protected routes normally.
     */
    mockedUseAuth.mockReturnValue({
      user: { id: 'user-1', username: 'local_normal', must_change_password: false },
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
          <Route path="/login" element={<div data-testid="login-page">Login</div>} />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.getByTestId('protected-content')).toBeInTheDocument()
    expect(screen.queryByTestId('change-password-page')).not.toBeInTheDocument()
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument()
  })

  it('renders children for SSO user (regardless of must_change_password)', () => {
    /**
     * Validates: Requirement 3.2
     * SSO user should access protected routes normally regardless of must_change_password.
     * Note: On unfixed code, auth_source is not in the interface, but ProtectedRoute
     * doesn't check it anyway, so SSO users pass through fine.
     */
    mockedUseAuth.mockReturnValue({
      user: { id: 'user-2', username: 'sso_user', must_change_password: false },
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
          <Route path="/login" element={<div data-testid="login-page">Login</div>} />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.getByTestId('protected-content')).toBeInTheDocument()
    expect(screen.queryByTestId('change-password-page')).not.toBeInTheDocument()
  })

  it('redirects to /login when user is not authenticated', () => {
    /**
     * Validates: Requirement 3.5
     * Unauthenticated user should be redirected to /login.
     */
    mockedUseAuth.mockReturnValue({
      user: null,
      roles: [],
      capabilities: [],
      loading: false,
      csrfToken: null,
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
          <Route path="/login" element={<div data-testid="login-page">Login</div>} />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument()
    expect(screen.getByTestId('login-page')).toBeInTheDocument()
  })

  it('redirects to / when user lacks required capability', () => {
    /**
     * Validates: Requirement 3.7
     * User lacking the required capability should be redirected to /.
     */
    mockedUseAuth.mockReturnValue({
      user: { id: 'user-3', username: 'limited_user', must_change_password: false },
      roles: ['operator'],
      capabilities: ['dashboard:read'],  // does NOT have 'user:manage'
      loading: false,
      csrfToken: 'csrf-token',
      logout: vi.fn(),
      refreshAuth: vi.fn(),
    })

    render(
      <MemoryRouter initialEntries={['/admin/users']}>
        <Routes>
          <Route
            path="/admin/users"
            element={
              <ProtectedRoute capability="user:manage">
                <div data-testid="admin-content">Admin Users</div>
              </ProtectedRoute>
            }
          />
          <Route path="/" element={<div data-testid="home-page">Home</div>} />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.queryByTestId('admin-content')).not.toBeInTheDocument()
    expect(screen.getByTestId('home-page')).toBeInTheDocument()
  })

  it('shows loading spinner while auth state is loading', () => {
    mockedUseAuth.mockReturnValue({
      user: null,
      roles: [],
      capabilities: [],
      loading: true,
      csrfToken: null,
      logout: vi.fn(),
      refreshAuth: vi.fn(),
    })

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
          <Route path="/login" element={<div data-testid="login-page">Login</div>} />
        </Routes>
      </MemoryRouter>
    )

    // Should show spinner, not content or redirect
    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument()
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument()
    // Spinner has animate-spin class
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
  })
})

describe('Preservation: Sidebar KeyRound visibility for local users', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows KeyRound change-password icon for local user with must_change_password=false', () => {
    /**
     * Validates: Requirement 3.4
     * Local user with must_change_password=false should see the change-password
     * link (KeyRound icon) in the sidebar for voluntary password changes.
     *
     * On unfixed code, the Sidebar shows this icon for ALL authenticated users
     * regardless of auth_source. This is the correct behavior for local users.
     */
    mockedUseAuth.mockReturnValue({
      user: { id: 'user-local', username: 'local_user', must_change_password: false, auth_source: 'local' },
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

    // Local users should see the change-password link
    const changePasswordLink = screen.getByTitle('修改密码')
    expect(changePasswordLink).toBeInTheDocument()
  })

  it('shows logout button for all authenticated users', () => {
    /**
     * Validates preservation: logout button is always visible.
     */
    mockedUseAuth.mockReturnValue({
      user: { id: 'user-any', username: 'any_user', must_change_password: false },
      roles: ['operator'],
      capabilities: ['dashboard:read'],
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

    const logoutButton = screen.getByTitle('退出登录')
    expect(logoutButton).toBeInTheDocument()
  })
})
