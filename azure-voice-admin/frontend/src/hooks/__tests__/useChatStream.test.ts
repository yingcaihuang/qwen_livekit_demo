import { describe, it, expect, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useChatStream } from '../useChatStream'
import type { ChatParams } from '@/types'

// Validates: Requirements 2.2 (逐块解析并逐字追加 assistant 气泡), 2.3 (多轮上下文)

const DEFAULT_PARAMS: ChatParams = {
  system_prompt: '',
  temperature: 1,
  max_tokens: null,
}

/**
 * 构建一个假的 Response-like 对象：其 body.getReader() 会依次吐出给定的
 * Uint8Array 分片，全部读完后返回 { done: true }。
 */
function makeFakeResponse(chunks: Uint8Array[], ok = true, status = 200) {
  let i = 0
  const reader = {
    read: () =>
      Promise.resolve(
        i < chunks.length
          ? { done: false, value: chunks[i++] }
          : { done: true, value: undefined },
      ),
    cancel: () => Promise.resolve(),
  }
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    body: { getReader: () => reader },
  } as unknown as Response
}

/** 将一组 SSE 帧编码为字节；每帧以 `data: {json}\n\n` 形式拼接 */
function encodeFrames(frames: string[]): Uint8Array {
  return new TextEncoder().encode(frames.join(''))
}

function frame(obj: unknown): string {
  return `data: ${JSON.stringify(obj)}\n\n`
}

function mockFetchOnce(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('useChatStream', () => {
  it('parses an SSE stream and assembles incremental assistant content', async () => {
    const bytes = encodeFrames([
      frame({ type: 'session', session_id: 'sess-123' }),
      frame({ type: 'delta', content: 'Hello' }),
      frame({ type: 'delta', content: ' world' }),
      frame({ type: 'done', usage: { input_tokens: 10, output_tokens: 5 } }),
    ])
    mockFetchOnce(makeFakeResponse([bytes]))

    const { result } = renderHook(() => useChatStream('inst-1'))

    await act(async () => {
      await result.current.sendMessage('Hi there', DEFAULT_PARAMS)
    })

    expect(result.current.messages).toEqual([
      { role: 'user', content: 'Hi there' },
      { role: 'assistant', content: 'Hello world' },
    ])
    expect(result.current.sessionId).toBe('sess-123')
    expect(result.current.usage).toEqual({ input_tokens: 10, output_tokens: 5 })
    expect(result.current.streaming).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('reassembles frames split across multiple reader chunks', async () => {
    // Build the full byte stream then split it at an awkward boundary so that
    // a single SSE frame (and the \n\n separator) straddles two chunks.
    const full = encodeFrames([
      frame({ type: 'session', session_id: 'sess-xyz' }),
      frame({ type: 'delta', content: 'Strea' }),
      frame({ type: 'delta', content: 'ming!' }),
      frame({ type: 'done', usage: { input_tokens: 3, output_tokens: 7 } }),
    ])
    // Split mid-way through the payload (not on a frame boundary).
    const splitAt = Math.floor(full.length / 2)
    const first = full.slice(0, splitAt)
    const second = full.slice(splitAt)
    mockFetchOnce(makeFakeResponse([first, second]))

    const { result } = renderHook(() => useChatStream('inst-1'))

    await act(async () => {
      await result.current.sendMessage('go', DEFAULT_PARAMS)
    })

    expect(result.current.messages).toEqual([
      { role: 'user', content: 'go' },
      { role: 'assistant', content: 'Streaming!' },
    ])
    expect(result.current.sessionId).toBe('sess-xyz')
    expect(result.current.usage).toEqual({ input_tokens: 3, output_tokens: 7 })
    expect(result.current.error).toBeNull()
  })

  it('handles a \\n\\n separator that is split across chunks', async () => {
    const f1 = frame({ type: 'delta', content: 'A' })
    const f2 = frame({ type: 'delta', content: 'B' })
    const joined = f1 + f2
    // Cut right between the two newlines of the first frame separator.
    const boundary = f1.length - 1 // between the two '\n'
    const first = new TextEncoder().encode(joined.slice(0, boundary))
    const second = new TextEncoder().encode(joined.slice(boundary))
    mockFetchOnce(makeFakeResponse([first, second]))

    const { result } = renderHook(() => useChatStream('inst-1'))

    await act(async () => {
      await result.current.sendMessage('x', DEFAULT_PARAMS)
    })

    expect(result.current.messages[1]).toEqual({
      role: 'assistant',
      content: 'AB',
    })
  })

  it('sets error state when an error event is received and ends streaming', async () => {
    const bytes = encodeFrames([
      frame({ type: 'session', session_id: 'sess-err' }),
      frame({ type: 'delta', content: 'partial' }),
      frame({ type: 'error', message: 'Azure upstream failed' }),
    ])
    mockFetchOnce(makeFakeResponse([bytes]))

    const { result } = renderHook(() => useChatStream('inst-1'))

    await act(async () => {
      await result.current.sendMessage('trigger error', DEFAULT_PARAMS)
    })

    expect(result.current.error).toBe('Azure upstream failed')
    expect(result.current.streaming).toBe(false)
  })

  it('loadSession preloads messages and reuses session_id on the next send', async () => {
    const bytes = encodeFrames([
      frame({ type: 'delta', content: 'continued' }),
      frame({ type: 'done', usage: { input_tokens: 4, output_tokens: 6 } }),
    ])
    const fetchMock = mockFetchOnce(makeFakeResponse([bytes]))

    const { result } = renderHook(() => useChatStream('inst-1'))

    act(() => {
      result.current.loadSession('sess-resume', [
        { role: 'user', content: '之前的问题' },
        { role: 'assistant', content: '之前的回答' },
      ])
    })

    expect(result.current.sessionId).toBe('sess-resume')
    expect(result.current.messages).toEqual([
      { role: 'user', content: '之前的问题' },
      { role: 'assistant', content: '之前的回答' },
    ])

    await act(async () => {
      await result.current.sendMessage('新的问题', DEFAULT_PARAMS)
    })

    // 请求体应带上续聊的 session_id，并把新消息追加到已有历史之后
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)
    expect(body.session_id).toBe('sess-resume')
    expect(body.messages).toEqual([
      { role: 'user', content: '之前的问题' },
      { role: 'assistant', content: '之前的回答' },
      { role: 'user', content: '新的问题' },
    ])
  })

  it('includes the model in the request body when provided, omits it otherwise', async () => {
    // 传入 model 时，请求体应带上 model
    const bytesA = encodeFrames([
      frame({ type: 'delta', content: 'ok' }),
      frame({ type: 'done', usage: { input_tokens: 1, output_tokens: 1 } }),
    ])
    const fetchMockA = mockFetchOnce(makeFakeResponse([bytesA]))
    const { result: resultA } = renderHook(() => useChatStream('inst-1'))

    await act(async () => {
      await resultA.current.sendMessage('hi', DEFAULT_PARAMS, 'gpt-4o')
    })

    const bodyA = JSON.parse((fetchMockA.mock.calls[0][1] as RequestInit).body as string)
    expect(bodyA.model).toBe('gpt-4o')

    vi.unstubAllGlobals()

    // 未传入 model 时，请求体不应包含 model 键
    const bytesB = encodeFrames([
      frame({ type: 'delta', content: 'ok' }),
      frame({ type: 'done', usage: { input_tokens: 1, output_tokens: 1 } }),
    ])
    const fetchMockB = mockFetchOnce(makeFakeResponse([bytesB]))
    const { result: resultB } = renderHook(() => useChatStream('inst-1'))

    await act(async () => {
      await resultB.current.sendMessage('hi', DEFAULT_PARAMS)
    })

    const bodyB = JSON.parse((fetchMockB.mock.calls[0][1] as RequestInit).body as string)
    expect('model' in bodyB).toBe(false)
  })

  it('newConversation clears messages, sessionId, usage and error', async () => {
    const bytes = encodeFrames([
      frame({ type: 'session', session_id: 'sess-clear' }),
      frame({ type: 'delta', content: 'hi' }),
      frame({ type: 'done', usage: { input_tokens: 1, output_tokens: 2 } }),
    ])
    mockFetchOnce(makeFakeResponse([bytes]))

    const { result } = renderHook(() => useChatStream('inst-1'))

    await act(async () => {
      await result.current.sendMessage('hello', DEFAULT_PARAMS)
    })

    // Sanity: state populated before clearing.
    expect(result.current.messages.length).toBe(2)
    expect(result.current.sessionId).toBe('sess-clear')

    act(() => {
      result.current.newConversation()
    })

    expect(result.current.messages).toEqual([])
    expect(result.current.sessionId).toBeNull()
    expect(result.current.usage).toBeNull()
    expect(result.current.error).toBeNull()
    expect(result.current.streaming).toBe(false)
  })
})
