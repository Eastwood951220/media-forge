import { useCallback, useEffect, useState } from 'react'
import { App } from 'antd'
import { fetchMovieFilterConfig, updateMovieFilterConfig } from '@/api/movie'
import type { MovieFilterConfig, MovieFilterField } from '@/api/movie/types'

export function useMovieFilterConfig() {
  const { message } = App.useApp()
  const [config, setConfig] = useState<MovieFilterConfig>({})
  const [loading, setLoading] = useState(true)
  const [loaded, setLoaded] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    let cancelled = false

    setLoading(true)
    setLoaded(false)

    fetchMovieFilterConfig()
      .then((result) => {
        if (cancelled) return
        setConfig(result.filters ?? {})
      })
      .catch(() => {
        if (cancelled) return
        setConfig({})
        message.error('加载筛选配置失败')
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
        setLoaded(true)
      })

    return () => {
      cancelled = true
    }
  }, [message])

  const toggle = useCallback(async (key: MovieFilterField, visible: boolean) => {
    const previous = config
    const updated: MovieFilterConfig = {
      ...config,
      [key]: { ...(config[key] ?? {}), visible },
    }
    setConfig(updated)
    try {
      await updateMovieFilterConfig(updated)
    } catch {
      setConfig(previous)
      message.error('保存筛选配置失败')
    }
  }, [config, message])

  return {
    config,
    loading,
    loaded,
    drawerOpen,
    setDrawerOpen,
    toggle,
    setConfig,
  }
}

export type MovieFilterConfigState = ReturnType<typeof useMovieFilterConfig>
