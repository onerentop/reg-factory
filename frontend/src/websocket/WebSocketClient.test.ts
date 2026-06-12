import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { WebSocketClient } from '@/websocket/WebSocketClient'

// ── Fake WebSocket instance ───────────────────────────────────────────────────
class FakeWS {
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  readyState: number = 1 // starts OPEN
  url: string
  onopen: ((e: any) => void) | null = null
  onmessage: ((e: any) => void) | null = null
  onclose: ((e: any) => void) | null = null
  onerror: ((e: any) => void) | null = null
  sentMessages: string[] = []
  closeCalled = false

  constructor(url: string) {
    this.url = url
  }

  send(data: string) {
    this.sentMessages.push(data)
  }

  close() {
    this.closeCalled = true
    this.readyState = FakeWS.CLOSED
  }

  // test helpers
  triggerOpen() { this.onopen?.({}) }
  triggerMessage(data: any) { this.onmessage?.({ data: JSON.stringify(data) }) }
  triggerClose() {
    this.readyState = FakeWS.CLOSED
    this.onclose?.({})
  }
}

// Track the most recently constructed FakeWS
let lastFakeWS: FakeWS | null = null
let constructCount = 0

// We need a real class that can be called with `new`, with static constants
class SpyWebSocket extends FakeWS {
  static override OPEN = FakeWS.OPEN
  static override CLOSING = FakeWS.CLOSING
  static override CLOSED = FakeWS.CLOSED

  constructor(url: string) {
    super(url)
    lastFakeWS = this
    constructCount++
  }
}

// ── Setup ─────────────────────────────────────────────────────────────────────
beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('WebSocket', SpyWebSocket)
  lastFakeWS = null
  constructCount = 0
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('WebSocketClient — connect', () => {
  it('connect 创建 WebSocket，传入正确 url', () => {
    const client = new WebSocketClient('ws://test-host/ws')
    client.connect()
    expect(constructCount).toBe(1)
    expect(lastFakeWS!.url).toBe('ws://test-host/ws')
  })

  it('已 OPEN 时再次 connect 不重新创建 WebSocket', () => {
    const client = new WebSocketClient('ws://test/ws')
    client.connect()
    const first = lastFakeWS
    // readyState is still OPEN (1)
    client.connect()
    expect(constructCount).toBe(1)
    expect(lastFakeWS).toBe(first)
  })

  it('onopen 触发后不抛出', () => {
    const client = new WebSocketClient('ws://test/ws')
    client.connect()
    expect(() => lastFakeWS!.triggerOpen()).not.toThrow()
  })
})

describe('WebSocketClient — on / 消息分发', () => {
  it('注册 handler，收到匹配 type 消息时调用', () => {
    const client = new WebSocketClient('ws://test/ws')
    client.connect()

    const handler = vi.fn()
    client.on('registration', handler)

    lastFakeWS!.triggerMessage({ type: 'registration', data: { id: '42' } })
    expect(handler).toHaveBeenCalledOnce()
    expect(handler).toHaveBeenCalledWith({ id: '42' })
  })

  it('不同 type 不触发无关 handler', () => {
    const client = new WebSocketClient('ws://test/ws')
    client.connect()

    const handler = vi.fn()
    client.on('alert', handler)

    lastFakeWS!.triggerMessage({ type: 'registration', data: {} })
    expect(handler).not.toHaveBeenCalled()
  })

  it('* 通配符接收所有消息（接收完整 msg）', () => {
    const client = new WebSocketClient('ws://test/ws')
    client.connect()

    const wildcard = vi.fn()
    client.on('*', wildcard)

    lastFakeWS!.triggerMessage({ type: 'anything', data: { x: 1 } })
    expect(wildcard).toHaveBeenCalledOnce()
    expect(wildcard).toHaveBeenCalledWith({ type: 'anything', data: { x: 1 } })
  })

  it('on 返回的 unsubscribe 移除 handler', () => {
    const client = new WebSocketClient('ws://test/ws')
    client.connect()

    const handler = vi.fn()
    const unsub = client.on('test-event', handler)
    unsub()

    lastFakeWS!.triggerMessage({ type: 'test-event', data: {} })
    expect(handler).not.toHaveBeenCalled()
  })

  it('消息无 type 字段时使用 "unknown"', () => {
    const client = new WebSocketClient('ws://test/ws')
    client.connect()

    const handler = vi.fn()
    client.on('unknown', handler)

    lastFakeWS!.triggerMessage({ data: 'no-type' })
    expect(handler).toHaveBeenCalledOnce()
  })

  it('非法 JSON 不抛出', () => {
    const client = new WebSocketClient('ws://test/ws')
    client.connect()

    expect(() =>
      lastFakeWS!.onmessage?.({ data: 'not-json{{' }),
    ).not.toThrow()
  })
})

describe('WebSocketClient — send', () => {
  it('OPEN 状态下 send 传递 JSON 字符串', () => {
    const client = new WebSocketClient('ws://test/ws')
    client.connect()

    client.send({ action: 'ping' })
    expect(lastFakeWS!.sentMessages).toHaveLength(1)
    expect(JSON.parse(lastFakeWS!.sentMessages[0])).toEqual({ action: 'ping' })
  })

  it('非 OPEN 状态下 send 不调用 ws.send', () => {
    const client = new WebSocketClient('ws://test/ws')
    client.connect()
    lastFakeWS!.readyState = FakeWS.CLOSED

    client.send({ action: 'ping' })
    expect(lastFakeWS!.sentMessages).toHaveLength(0)
  })
})

describe('WebSocketClient — disconnect', () => {
  it('disconnect 调用 ws.close', () => {
    const client = new WebSocketClient('ws://test/ws')
    client.connect()
    const ws = lastFakeWS!

    client.disconnect()
    expect(ws.closeCalled).toBe(true)
  })

  it('disconnect 后 send 不抛出', () => {
    const client = new WebSocketClient('ws://test/ws')
    client.connect()
    client.disconnect()
    expect(() => client.send({ x: 1 })).not.toThrow()
  })
})

describe('WebSocketClient — 自动重连', () => {
  it('onclose 触发后 reconnectInterval ms 后重新 connect', () => {
    const client = new WebSocketClient('ws://test/ws')
    client.connect()
    expect(constructCount).toBe(1)

    // 断线
    lastFakeWS!.triggerClose()

    // 推进定时器
    vi.advanceTimersByTime(3000)
    expect(constructCount).toBe(2)
  })

  it('disconnect 取消待重连 timer，不再重连', () => {
    const client = new WebSocketClient('ws://test/ws')
    client.connect()

    lastFakeWS!.triggerClose()
    // 在 timer 触发前 disconnect（disconnect 会 clearTimeout）
    client.disconnect()
    vi.advanceTimersByTime(5000)
    // 仍然只创建了 1 个 WS
    expect(constructCount).toBe(1)
  })
})
