import { describe, it, expect, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { Toaster, toast } from '../toast'

describe('toast store + Toaster', () => {
  it('renders a pushed toast with its title and description', () => {
    render(<Toaster />)
    act(() => {
      toast({ title: '已加入生成队列', description: '任务在后台生成' })
    })
    expect(screen.getByText('已加入生成队列')).toBeInTheDocument()
    expect(screen.getByText('任务在后台生成')).toBeInTheDocument()
    // Accessible live region
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('invokes the action callback when the action button is clicked', () => {
    const onClick = vi.fn()
    render(<Toaster />)
    act(() => {
      toast({ title: '查看队列测试', action: { label: '查看队列', onClick } })
    })
    act(() => {
      screen.getByRole('button', { name: '查看队列' }).click()
    })
    expect(onClick).toHaveBeenCalledTimes(1)
  })
})
