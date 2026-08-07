import { useState, useEffect, useCallback } from 'react'

interface UseApiResult<T> {
  data: T | null
  error: Error | null
  loading: boolean
  refetch: () => void
}

export function useApi<T>(url: string): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [loading, setLoading] = useState<boolean>(true)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(url)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
      const json = (await response.json()) as T
      setData(json)
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)))
    } finally {
      setLoading(false)
    }
  }, [url])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return { data, error, loading, refetch: fetchData }
}
