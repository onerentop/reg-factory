import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'

// ── vi.hoisted: 确保 mock 变量在 vi.mock factory 被 hoist 前已初始化 ──────────
const { mockConnect, mockOn } = vi.hoisted(() => ({
  mockConnect: vi.fn(),
  mockOn: vi.fn(),
}))

// vi.mock 必须在顶层且 factory 内只能使用 hoisted 变量
vi.mock('@/websocket/WebSocketClient', () => ({
  WebSocketClient: vi.fn(),
  wsClient: {
    connect: mockConnect,
    on: mockOn,
  },
}))

// 在 mock 声明之后才导入被测 hook
import { useWebSocket, useAlert, useRegistrationEvent } from '@/hooks/useWebSocket'

beforeEach(() => {
  mockConnect.mockClear()
  mockOn.mockClear()
  // 默认：on 返回 no-op unsubscribe
  mockOn.mockReturnValue(() => {})
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('useWebSocket — 挂载', () => {
  it('mount 时调用 wsClient.connect()', () => {
    renderHook(() => useWebSocket('test-event', vi.fn()))
    expect(mockConnect).toHaveBeenCalledOnce()
  })

  it('mount 时调用 wsClient.on(eventType, handler)', () => {
    renderHook(() => useWebSocket('my-event', vi.fn()))
    expect(mockOn).toHaveBeenCalledOnce()
    expect(mockOn.mock.calls[0][0]).toBe('my-event')
  })
})

describe('useWebSocket — 卸载', () => {
  it('unmount 时调用 on 返回的 unsubscribe', () => {
    const unsubscribe = vi.fn()
    mockOn.mockReturnValueOnce(unsubscribe)

    const { unmount } = renderHook(() => useWebSocket('test-event', vi.fn()))
    unmount()
    expect(unsubscribe).toHaveBeenCalledOnce()
  })
})

describe('useWebSocket — handler 调用', () => {
  it('wsClient.on 注册的 wrapper 调用最新的 handler', () => {
    const handler = vi.fn()
    // 捕获注册到 wsClient 的 wrapper
    let capturedWrapper: ((data: any) => void) | undefined

    mockOn.mockImplementation((_type: string, wrapper: (data: any) => void) => {
      capturedWrapper = wrapper
      return () => {}
    })

    renderHook(() => useWebSocket('alert', handler))

    act(() => {
      capturedWrapper?.({ msg: 'hello' })
    })

    expect(handler).toHaveBeenCalledOnce()
    expect(handler).toHaveBeenCalledWith({ msg: 'hello' })
  })
})

describe('useAlert', () => {
  it('订阅 "alert" 事件', () => {
    renderHook(() => useAlert(vi.fn()))
    expect(mockOn).toHaveBeenCalledWith('alert', expect.any(Function))
  })
})

describe('useRegistrationEvent', () => {
  it('订阅 "registration" 事件', () => {
    renderHook(() => useRegistrationEvent(vi.fn()))
    expect(mockOn).toHaveBeenCalledWith('registration', expect.any(Function))
  })
})
