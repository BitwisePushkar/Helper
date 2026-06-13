import { useEffect, useRef, useCallback, useState } from 'react'

const BACKEND_WS = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'
const HEARTBEAT_MS = 20_000
const MAX_RETRIES = 8
const BASE_BACKOFF_MS = 500

/**
 * useWebSocket — manages a single WebSocket connection per session.
 *
 * Features:
 *  - Exponential back-off reconnection (capped at ~30s)
 *  - Heartbeat ping to detect silent disconnects
 *  - onMessage dispatcher keyed by frame type
 *  - Exposes sendTranscript() and disconnect() to caller
 *  - Tracks connection status for UI feedback
 */
export function useWebSocket({ sessionId, onMessage }) {
  const wsRef = useRef(null)
  const retriesRef = useRef(0)
  const heartbeatRef = useRef(null)
  const [status, setStatus] = useState('disconnected') // 'connecting' | 'connected' | 'disconnected' | 'error'

  const clearHeartbeat = () => {
    if (heartbeatRef.current) clearInterval(heartbeatRef.current)
  }

  const connect = useCallback(() => {
    if (!sessionId) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    setStatus('connecting')
    const url = `${BACKEND_WS}/ws/${sessionId}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      retriesRef.current = 0
      setStatus('connected')

      // Start heartbeat
      clearHeartbeat()
      heartbeatRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }))
        }
      }, HEARTBEAT_MS)
    }

    ws.onmessage = (event) => {
      try {
        const frame = JSON.parse(event.data)
        onMessage?.(frame)
      } catch {
        console.warn('[WS] Could not parse frame:', event.data)
      }
    }

    ws.onerror = (e) => {
      console.error('[WS] Error', e)
      setStatus('error')
    }

    ws.onclose = (e) => {
      clearHeartbeat()
      setStatus('disconnected')

      // Do not reconnect if server closed cleanly (code 1000) or we called disconnect()
      if (e.code === 1000) return

      const retries = retriesRef.current
      if (retries >= MAX_RETRIES) {
        console.error('[WS] Max retries reached')
        setStatus('error')
        return
      }

      const delay = Math.min(BASE_BACKOFF_MS * 2 ** retries, 30_000)
      console.info(`[WS] Reconnecting in ${delay}ms (attempt ${retries + 1})`)
      retriesRef.current += 1
      setTimeout(connect, delay)
    }
  }, [sessionId, onMessage])

  useEffect(() => {
    connect()
    return () => {
      clearHeartbeat()
      wsRef.current?.close(1000)
    }
  }, [connect])

  const sendTranscript = useCallback((text, speaker = 'user') => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return false
    wsRef.current.send(JSON.stringify({ type: 'transcript', text, speaker }))
    return true
  }, [])

  const sendFrame = useCallback((frame) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return false
    wsRef.current.send(JSON.stringify(frame))
    return true
  }, [])

  const disconnect = useCallback(() => {
    clearHeartbeat()
    wsRef.current?.close(1000)
  }, [])

  return { status, sendTranscript, sendFrame, disconnect }
}
