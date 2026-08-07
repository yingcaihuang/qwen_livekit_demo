import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ImageEmptyState } from '../ImageEmptyState'
import { ImageParamsPanel } from '../ImageParamsPanel'
import { ImageResultGrid } from '../ImageResultGrid'
import type { ImageParams, ImageGeneration } from '@/types'

function makeParams(overrides: Partial<ImageParams> = {}): ImageParams {
  return {
    size: '1024x1024',
    quality: 'high',
    output_format: 'png',
    compression: 100,
    n: 1,
    ...overrides,
  }
}

// Validates: Requirements 4.4 (empty state prompts the user to generate an image)
describe('ImageEmptyState', () => {
  it('renders the "Generate an image to get started" prompt', () => {
    render(<ImageEmptyState />)
    expect(
      screen.getByText('Generate an image to get started'),
    ).toBeInTheDocument()
  })
})

// Validates: Requirements 4.7 (compression constrained to [0,100]) and 4.6 (variations >= 1)
describe('ImageParamsPanel', () => {
  it('shows the default compression value of 100', () => {
    render(
      <ImageParamsPanel params={makeParams({ compression: 100 })} onChange={vi.fn()} />,
    )
    const slider = screen.getByLabelText('Compression Level') as HTMLInputElement
    expect(slider.value).toBe('100')
    // The numeric readout next to the label also reflects 100
    expect(screen.getByText('100')).toBeInTheDocument()
  })

  it('clamps an above-range compression value to 100', () => {
    const onChange = vi.fn()
    // Start below the max so an out-of-range change actually fires an event
    // (jsdom pre-clamps range inputs, and React skips no-op changes).
    render(<ImageParamsPanel params={makeParams({ compression: 50 })} onChange={onChange} />)
    const slider = screen.getByLabelText('Compression Level')
    fireEvent.change(slider, { target: { value: '250' } })
    expect(onChange).toHaveBeenCalledTimes(1)
    const emitted = onChange.mock.calls[0][0] as Partial<ImageParams>
    expect(emitted.compression).toBeLessThanOrEqual(100)
    expect(emitted.compression).toBeGreaterThanOrEqual(0)
    expect(emitted.compression).toBe(100)
  })

  it('clamps a below-range compression value to 0', () => {
    const onChange = vi.fn()
    render(<ImageParamsPanel params={makeParams()} onChange={onChange} />)
    const slider = screen.getByLabelText('Compression Level')
    fireEvent.change(slider, { target: { value: '-40' } })
    expect(onChange).toHaveBeenCalledTimes(1)
    const emitted = onChange.mock.calls[0][0] as Partial<ImageParams>
    expect(emitted.compression).toBeGreaterThanOrEqual(0)
    expect(emitted.compression).toBeLessThanOrEqual(100)
    expect(emitted.compression).toBe(0)
  })

  it('keeps an in-range compression value unchanged', () => {
    const onChange = vi.fn()
    render(<ImageParamsPanel params={makeParams()} onChange={onChange} />)
    const slider = screen.getByLabelText('Compression Level')
    fireEvent.change(slider, { target: { value: '55' } })
    expect(onChange).toHaveBeenCalledWith({ compression: 55 })
  })

  it('renders an Image Format dropdown with a png option', () => {
    render(<ImageParamsPanel params={makeParams()} onChange={vi.fn()} />)
    const select = screen.getByLabelText('Image Format') as HTMLSelectElement
    expect(select).toBeInTheDocument()
    expect(select.value).toBe('png')
  })

  it('shows the default variation count of 1', () => {
    render(<ImageParamsPanel params={makeParams({ n: 1 })} onChange={vi.fn()} />)
    const slider = screen.getByLabelText('Number of variations') as HTMLInputElement
    expect(slider.value).toBe('1')
  })

  it('clamps the variation count to be at least 1', () => {
    const onChange = vi.fn()
    // Start above the min so an out-of-range change actually fires an event.
    render(<ImageParamsPanel params={makeParams({ n: 3 })} onChange={onChange} />)
    const slider = screen.getByLabelText('Number of variations')
    fireEvent.change(slider, { target: { value: '0' } })
    expect(onChange).toHaveBeenCalledTimes(1)
    const emitted = onChange.mock.calls[0][0] as Partial<ImageParams>
    expect(emitted.n).toBeGreaterThanOrEqual(1)
  })
})

// Validates: Requirements 4.6 (multiple variations rendered as a grid of results)
describe('ImageResultGrid', () => {
  function makeResult(overrides: Partial<ImageGeneration> = {}): ImageGeneration {
    return {
      generation_id: 'x',
      instance_id: 'inst-1',
      prompt: 'a cat',
      params: makeParams(),
      images: ['/api/images/x/0', '/api/images/x/1'],
      input_tokens: 0,
      output_tokens: 0,
      has_reference: false,
      created_at: '2024-01-01T00:00:00Z',
      ...overrides,
    }
  }

  it('renders one <img> per image URL with matching src values', () => {
    render(<ImageResultGrid result={makeResult()} />)
    const imgs = screen.getAllByRole('img')
    expect(imgs).toHaveLength(2)
    const srcs = imgs.map((img) => (img as HTMLImageElement).getAttribute('src'))
    expect(srcs).toEqual(['/api/images/x/0', '/api/images/x/1'])
  })

  it('renders no images when the result has an empty image list', () => {
    render(<ImageResultGrid result={makeResult({ images: [] })} />)
    expect(screen.queryAllByRole('img')).toHaveLength(0)
  })
})
