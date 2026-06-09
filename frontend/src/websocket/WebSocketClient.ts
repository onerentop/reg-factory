type EventHandler = (data: any) => void

export class WebSocketClient {
  private ws: WebSocket | null = null
  private url: string
  private handlers: Map<string, EventHandler[]> = new Map()
  private reconnectTimer: number | null = null
  private reconnectInterval = 3000

  constructor(url: string = `ws://${window.location.host}/ws`) {
    this.url = url
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return

    this.ws = new WebSocket(this.url)

    this.ws.onopen = () => {
      console.log('WebSocket connected')
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer)
        this.reconnectTimer = null
      }
    }

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        const type = msg.type || 'unknown'
        const handlers = this.handlers.get(type) || []
        handlers.forEach((h) => h(msg.data))
        const allHandlers = this.handlers.get('*') || []
        allHandlers.forEach((h) => h(msg))
      } catch (e) {
        console.error('WebSocket parse error:', e)
      }
    }

    this.ws.onclose = () => {
      console.log('WebSocket disconnected, reconnecting...')
      this.reconnectTimer = window.setTimeout(() => this.connect(), this.reconnectInterval)
    }

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }
  }

  on(eventType: string, handler: EventHandler): () => void {
    const handlers = this.handlers.get(eventType) || []
    handlers.push(handler)
    this.handlers.set(eventType, handlers)
    return () => {
      const idx = handlers.indexOf(handler)
      if (idx >= 0) handlers.splice(idx, 1)
    }
  }

  send(data: any): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
    }
    this.ws?.close()
    this.ws = null
  }
}

export const wsClient = new WebSocketClient()
