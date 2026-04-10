import { useState, useEffect } from 'react'

const REFRESH_INTERVAL = 10000 // 10秒

export function useAPI(endpoint, initialData = null) {
  const [data, setData] = useState(initialData)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdate, setLastUpdate] = useState(null)

  useEffect(() => {
    let mounted = true
    const controller = new AbortController()

    const fetchData = async () => {
      try {
        const resp = await fetch(`/api${endpoint}`, { signal: controller.signal })
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const json = await resp.json()
        if (mounted) {
          setData(json)
          setError(null)
          setLastUpdate(new Date().toLocaleTimeString())
        }
      } catch (e) {
        if (mounted && e.name !== 'AbortError') {
          setError(e.message)
        }
      } finally {
        if (mounted) setLoading(false)
      }
    }

    fetchData()
    const interval = setInterval(fetchData, REFRESH_INTERVAL)

    return () => {
      mounted = false
      controller.abort()
      clearInterval(interval)
    }
  }, [endpoint])

  return { data, loading, error, lastUpdate }
}

export function useMultiAPI(endpoints) {
  const [data, setData] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdate, setLastUpdate] = useState(null)

  useEffect(() => {
    let mounted = true
    const controller = new AbortController()

    const fetchAll = async () => {
      try {
        // 并行请求所有 API
        const entries = Object.entries(endpoints)
        const responses = await Promise.all(
          entries.map(([key, endpoint]) =>
            fetch(`/api${endpoint}`, { signal: controller.signal })
              .then(resp => resp.ok ? resp.json() : null)
              .catch(() => null)
          )
        )

        const results = {}
        entries.forEach(([key], i) => {
          if (responses[i]) results[key] = responses[i]
        })

        if (mounted) {
          setData(results)
          setError(null)
          setLoading(false)
          setLastUpdate(new Date().toLocaleTimeString())
        }
      } catch (e) {
        if (mounted && e.name !== 'AbortError') {
          setError(e.message)
          setLoading(false)
        }
      }
    }

    fetchAll()
    const interval = setInterval(fetchAll, REFRESH_INTERVAL)

    return () => {
      mounted = false
      controller.abort()
      clearInterval(interval)
    }
  }, [Object.values(endpoints).join(',')])

  return { data, loading, error, lastUpdate }
}