import { describe, expect, it } from 'vitest'
import { normalizeMathDelimiters } from '../MarkdownMessage'

describe('normalizeMathDelimiters', () => {
  it('converts display math \\[ ... \\] to block $$', () => {
    const out = normalizeMathDelimiters('前\\[ (a\\pm b)^2 \\]后')
    expect(out).toBe('前\n\n$$\n (a\\pm b)^2 \n$$\n\n后')
  })

  it('converts inline math \\( ... \\) to $ ... $', () => {
    expect(normalizeMathDelimiters('值 \\( x^2 \\) 结束')).toBe('值 $ x^2 $ 结束')
  })

  it('leaves fenced code blocks untouched', () => {
    const src = '```js\nconst a = arr\\[0\\]\n```'
    expect(normalizeMathDelimiters(src)).toBe(src)
  })

  it('leaves inline code untouched', () => {
    const src = 'use `arr\\[i\\]` here'
    expect(normalizeMathDelimiters(src)).toBe(src)
  })

  it('does not double-convert existing $ / $$ math', () => {
    const src = 'inline $x^2$ and $$y^2$$'
    expect(normalizeMathDelimiters(src)).toBe(src)
  })

  it('does not crash on unclosed delimiters during streaming', () => {
    expect(() => normalizeMathDelimiters('partial \\[ x^2')).not.toThrow()
    expect(normalizeMathDelimiters('partial \\[ x^2')).toBe('partial \n\n$$\n x^2')
  })
})
