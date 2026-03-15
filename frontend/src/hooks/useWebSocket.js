import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'

export function useWebSocket() {
  const queryClient = useQueryClient()
  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)

  useEffect(() => {
    function connect() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${location.host}/ws`)
      wsRef.current = ws

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (
            msg.type === 'transfer_start' ||
            msg.type === 'transfer_complete' ||
            msg.type === 'transfer_failed'
          ) {
            queryClient.invalidateQueries({ queryKey: ['dashboard'] })
            queryClient.invalidateQueries({ queryKey: ['transfers'] })
          }
          if (msg.type === 'tier_change') {
            queryClient.invalidateQueries({ queryKey: ['items'] })
            queryClient.invalidateQueries({ queryKey: ['series'] })
            queryClient.invalidateQueries({ queryKey: ['dashboard'] })
          }
        } catch (_) {}
      }

      ws.onclose = () => {
        reconnectTimer.current = setTimeout(connect, 3000)
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [queryClient])
}
