import { useEffect, useRef } from 'react'
import { wsClient } from '../websocket/WebSocketClient'

export function useWebSocket(eventType: string, handler: (data: any) => void) {
  const handlerRef = useRef(handler)
  handlerRef.current = handler

  useEffect(() => {
    wsClient.connect()
    const unsubscribe = wsClient.on(eventType, (data) => handlerRef.current(data))
    return unsubscribe
  }, [eventType])
}

export function useAlert(handler: (data: any) => void) {
  return useWebSocket('alert', handler)
}

export function useRegistrationEvent(handler: (data: any) => void) {
  return useWebSocket('registration', handler)
}
