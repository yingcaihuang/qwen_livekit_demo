import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { Instance, InstanceType } from '@/types'

// Mock react-router's useNavigate so we can assert the destination the
// "Start" button routes to per instance type.
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

import { InstanceCard } from '../InstanceCard'

function makeInstance(type: InstanceType, id = 'inst-123'): Instance {
  return {
    id,
    name: 'Test Instance',
    endpoint: 'https://example.openai.azure.com',
    deployment: 'gpt-test',
    type,
    description: 'desc',
    created_at: new Date().toISOString(),
  }
}

// Validates: Requirements 1.3, 1.4, 1.5 (type-based routing to the matching playground)
describe('InstanceCard start-button routing', () => {
  beforeEach(() => {
    mockNavigate.mockReset()
  })

  const routing: Array<{ type: InstanceType; label: RegExp; route: string }> = [
    { type: 'voice', label: /Start Session/i, route: '/sessions/new' },
    { type: 'chat', label: /开始对话/, route: '/chat/new' },
    { type: 'image', label: /生成图像/, route: '/images/new' },
  ]

  it.each(routing)(
    'routes a "$type" instance to $route with the instance id',
    async ({ type, label, route }) => {
      const user = userEvent.setup()
      render(
        <MemoryRouter>
          <InstanceCard instance={makeInstance(type, 'abc-1')} onDelete={vi.fn()} />
        </MemoryRouter>
      )

      await user.click(screen.getByRole('button', { name: label }))

      expect(mockNavigate).toHaveBeenCalledTimes(1)
      expect(mockNavigate).toHaveBeenCalledWith(`${route}?instance=abc-1`)
    }
  )

  it('renders a type badge for the instance', () => {
    render(
      <MemoryRouter>
        <InstanceCard instance={makeInstance('image')} onDelete={vi.fn()} />
      </MemoryRouter>
    )
    expect(screen.getByText('图像')).toBeInTheDocument()
  })
})
