import { describe, it, expect } from 'vitest'
import { formatEndpoint } from '../format'

describe('formatEndpoint', () => {
  it('returns "" for empty / nullish input', () => {
    expect(formatEndpoint('')).toBe('')
    expect(formatEndpoint(null)).toBe('')
    expect(formatEndpoint(undefined)).toBe('')
  })

  it('returns the part after /openai/ and strips the query string', () => {
    expect(
      formatEndpoint('https://x.services.ai.azure.com/openai/v1/responses?api-version=1'),
    ).toBe('v1/responses')
  })

  it('handles nested paths after /openai/', () => {
    expect(
      formatEndpoint('https://x.services.ai.azure.com/openai/v1/chat/completions'),
    ).toBe('v1/chat/completions')
  })

  it('falls back to the pathname when /openai/ is absent', () => {
    expect(formatEndpoint('https://example.com/foo/bar?x=1')).toBe('foo/bar')
  })

  it('is robust against non-parseable / relative inputs', () => {
    expect(formatEndpoint('/openai/v1/responses')).toBe('v1/responses')
    expect(formatEndpoint('not a url')).toBe('not a url')
  })

  it('strips the hash fragment as well', () => {
    expect(formatEndpoint('https://x.azure.com/openai/v1/responses#frag')).toBe('v1/responses')
  })
})
