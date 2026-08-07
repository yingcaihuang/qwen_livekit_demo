import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

import { InstanceForm } from '../InstanceForm'

const TYPE_BUTTON_NAMES = [/语音/, /对话/, /图像/]

describe('InstanceForm type selector', () => {
  beforeEach(() => {
    mockNavigate.mockReset()
  })

  // Validates: Requirements 1.7 (type is immutable after creation → disabled in edit mode)
  it('disables all type options in edit mode', () => {
    render(
      <MemoryRouter>
        <InstanceForm
          mode="edit"
          instanceId="inst-1"
          initialData={{ name: 'X', endpoint: 'https://e', deployment: 'd', type: 'chat' }}
        />
      </MemoryRouter>
    )

    for (const name of TYPE_BUTTON_NAMES) {
      expect(screen.getByRole('button', { name })).toBeDisabled()
    }
    expect(screen.getByText('类型创建后不可修改')).toBeInTheDocument()
  })

  // Validates: Requirements 1.1, 1.6 (type selectable in create mode)
  it('allows selecting a type in create mode', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <InstanceForm mode="create" />
      </MemoryRouter>
    )

    const chatOption = screen.getByRole('button', { name: /对话/ })
    expect(chatOption).not.toBeDisabled()
    expect(chatOption).toHaveAttribute('aria-pressed', 'false')

    await user.click(chatOption)
    expect(chatOption).toHaveAttribute('aria-pressed', 'true')
  })

  // Validates: Requirements 1.2 (submitting without a type shows a required-type validation error)
  it('shows a validation error when submitting without a type in create mode', async () => {
    const user = userEvent.setup()
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    render(
      <MemoryRouter>
        <InstanceForm mode="create" />
      </MemoryRouter>
    )

    await user.click(screen.getByRole('button', { name: '创建' }))

    expect(await screen.findByText('请选择实例类型')).toBeInTheDocument()
    // validation failed → no network request issued
    expect(fetchSpy).not.toHaveBeenCalled()
    fetchSpy.mockRestore()
  })
})
