import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { HistoryItem } from '@/types'
import { SessionRow } from '../SessionRow'

function makeItem(status: string): HistoryItem {
  return {
    id: 'gen-1',
    type: 'image',
    instance_id: 'inst-1',
    instance_name: 'Test',
    title: 'a cat',
    start_time: '2024-01-01T00:00:00Z',
    input_tokens: 0,
    output_tokens: 0,
    status,
  }
}

function renderRow(status: string) {
  render(
    <MemoryRouter>
      <table>
        <tbody>
          <SessionRow item={makeItem(status)} onDelete={vi.fn()} />
        </tbody>
      </table>
    </MemoryRouter>,
  )
}

// Validates image async job status labels are mapped to friendly text.
describe('SessionRow image job status labels', () => {
  it.each([
    ['pending', '排队中'],
    ['processing', '生成中'],
    ['failed', '失败'],
  ])('renders %s as "%s"', (status, label) => {
    renderRow(status)
    expect(screen.getByText(label)).toBeInTheDocument()
  })
})
