import { useWebSocket } from '@vueuse/core'

type WSHandlers = {
  connected: (ws: WebSocket) => void
  disconnected: (ws: WebSocket, ev: CloseEvent) => void
  error: (ws: WebSocket, ev: Event) => void
  message: (ws: WebSocket, ev: MessageEvent) => void
}

let socket: ReturnType<typeof useWebSocket> | null = null

const listeners = {
  connected: new Set<WSHandlers['connected']>(),
  disconnected: new Set<WSHandlers['disconnected']>(),
  error: new Set<WSHandlers['error']>(),
  message: new Set<WSHandlers['message']>(),
}

export function useAppWebSocket() {
  if (!socket) {
    socket = useWebSocket('ws://localhost:8000', {
      autoReconnect: true,

      onConnected(ws) {
        listeners.connected.forEach(fn => fn(ws))
      },

      onDisconnected(ws, ev) {
        listeners.disconnected.forEach(fn => fn(ws, ev))
      },

      onError(ws, ev) {
        listeners.error.forEach(fn => fn(ws, ev))
      },

      onMessage(ws, ev) {
        listeners.message.forEach(fn => fn(ws, ev))
      },
    })
  }

  return {
    ...socket,

    onConnected(fn: WSHandlers['connected']) {
      listeners.connected.add(fn)
      return () => listeners.connected.delete(fn)
    },

    onDisconnected(fn: WSHandlers['disconnected']) {
      listeners.disconnected.add(fn)
      return () => listeners.disconnected.delete(fn)
    },

    onError(fn: WSHandlers['error']) {
      listeners.error.add(fn)
      return () => listeners.error.delete(fn)
    },

    onMessage(fn: WSHandlers['message']) {
      listeners.message.add(fn)
      return () => listeners.message.delete(fn)
    },
  }
}
