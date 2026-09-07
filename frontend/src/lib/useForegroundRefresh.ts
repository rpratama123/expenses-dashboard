import { useEffect, useEffectEvent } from 'react'

export function useForegroundRefresh(refresh: () => void, intervalMs = 60_000): void {
  const onRefresh = useEffectEvent(refresh)
  useEffect(() => {
    const refreshVisible = () => { if (document.visibilityState === 'visible') onRefresh() }
    const interval = window.setInterval(refreshVisible, intervalMs)
    window.addEventListener('online', refreshVisible)
    document.addEventListener('visibilitychange', refreshVisible)
    return () => {
      clearInterval(interval)
      window.removeEventListener('online', refreshVisible)
      document.removeEventListener('visibilitychange', refreshVisible)
    }
  }, [intervalMs])
}
