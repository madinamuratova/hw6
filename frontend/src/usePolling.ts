import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from './api.ts'

/**
 * Load data now and then every `intervalMs`.
 * Changing `key` (e.g. selecting another ticket) clears the old data; changing the interval does not.
 */
export function usePolling<T>(load: () => Promise<T>, intervalMs: number, key: unknown = null) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const loadRef = useRef(load)
  loadRef.current = load
  const latest = useRef(0) // ignore answers to requests that a newer request replaced

  const refresh = useCallback(async () => {
    const id = ++latest.current
    try {
      const result = await loadRef.current()
      if (id === latest.current) {
        setData(result)
        setError(null)
      }
    } catch (e) {
      if (id === latest.current) setError(e instanceof ApiError ? e : new ApiError(0, String(e)))
    }
  }, [])

  useEffect(() => {
    setData(null)
    setError(null)
  }, [key])

  useEffect(() => {
    void refresh()
    const timer = setInterval(refresh, intervalMs)
    return () => clearInterval(timer)
  }, [refresh, intervalMs, key])

  return { data, error, refresh }
}
