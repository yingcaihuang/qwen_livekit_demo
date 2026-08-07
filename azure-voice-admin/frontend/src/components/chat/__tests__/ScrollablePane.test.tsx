import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ScrollablePane } from '../ScrollablePane'

describe('ScrollablePane', () => {
  it('renders children inside the scroll container', () => {
    render(
      <ScrollablePane>
        <p>可平移内容</p>
      </ScrollablePane>
    )
    expect(screen.getByText('可平移内容')).toBeInTheDocument()
  })

  it('hides arrows when content does not overflow (jsdom reports 0 sizes)', () => {
    render(
      <ScrollablePane>
        <p>短内容</p>
      </ScrollablePane>
    )
    // 无溢出时四个方向的箭头都不应渲染。
    expect(screen.queryByLabelText('向上滚动')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('向下滚动')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('向左滚动')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('向右滚动')).not.toBeInTheDocument()
  })
})
