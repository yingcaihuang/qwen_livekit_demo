import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TypeBadge, getTypeLabel } from '../TypeBadge'
import type { InstanceType } from '@/types'

// Validates: Requirements 1.6 (type badge shown for each instance)
describe('TypeBadge', () => {
  const cases: Array<{ type: InstanceType; label: string }> = [
    { type: 'voice', label: '语音' },
    { type: 'chat', label: '对话' },
    { type: 'image', label: '图像' },
  ]

  it.each(cases)('renders the $label label for the "$type" type', ({ type, label }) => {
    render(<TypeBadge type={type} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('applies the type-specific gradient class', () => {
    const { container } = render(<TypeBadge type="chat" />)
    const badge = container.querySelector('span')
    expect(badge).not.toBeNull()
    // chat → 翠绿渐变
    expect(badge?.className).toContain('from-emerald-500')
    expect(badge?.className).toContain('to-teal-500')
  })

  it('getTypeLabel maps each type to its Chinese label', () => {
    expect(getTypeLabel('voice')).toBe('语音')
    expect(getTypeLabel('chat')).toBe('对话')
    expect(getTypeLabel('image')).toBe('图像')
  })
})
