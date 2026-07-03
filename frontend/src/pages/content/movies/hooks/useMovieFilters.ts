import { useCallback, useEffect, useMemo, useReducer, useState } from 'react'
import { App } from 'antd'
import { fetchFilters } from '@/api/movie'
import { getTaskDict } from '@/api/crawlTask'
import { MOVIE_FILTER_OPTION_TYPE } from '../constants'
import type { MovieFilterConfig, SelectOption } from '@/api/movie/types'
import { buildMovieFilterParams, type MovieFilterState } from '../utils/movieFilter'

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '请求失败'
}

type FilterAction =
  | { type: 'patch'; payload: Partial<MovieFilterState> }
  | { type: 'reset' }

type UseMovieFiltersOptions = {
  enabled?: boolean
  filterConfig?: MovieFilterConfig
}

const INITIAL_FILTER_STATE: MovieFilterState = {
  selectedTask: undefined,
  search: '',
  ratingMin: undefined,
  ratingMax: undefined,
  actorsCountMin: undefined,
  actorsCountMax: undefined,
  selectedActors: [],
  selectedActorsNot: [],
  selectedTags: [],
  selectedTagsNot: [],
  selectedDirectors: [],
  selectedDirectorsNot: [],
  selectedMakers: [],
  selectedMakersNot: [],
  selectedSeries: [],
  selectedSeriesNot: [],
  storageStatus: undefined,
  releaseDateFrom: null,
  releaseDateTo: null,
  createdAtFrom: null,
  createdAtTo: null,
}

function filterReducer(state: MovieFilterState, action: FilterAction): MovieFilterState {
  switch (action.type) {
    case 'patch':
      return { ...state, ...action.payload }
    case 'reset':
      return { ...INITIAL_FILTER_STATE }
    default:
      return state
  }
}

function toOptions(values: string[]): SelectOption[] {
  return values.map((value) => ({ value, label: value }))
}

function isVisible(config: MovieFilterConfig | undefined, key: string): boolean {
  return config?.[key as keyof MovieFilterConfig]?.visible !== false
}

export function useMovieFilters(options: UseMovieFiltersOptions = {}) {
  const { message } = App.useApp()
  const enabled = options.enabled ?? true
  const filterConfig = options.filterConfig
  const [form, dispatch] = useReducer(filterReducer, INITIAL_FILTER_STATE)
  const [taskOptions, setTaskOptions] = useState<SelectOption[]>([])
  const [actorOptions, setActorOptions] = useState<SelectOption[]>([])
  const [tagOptions, setTagOptions] = useState<SelectOption[]>([])
  const [directorOptions, setDirectorOptions] = useState<SelectOption[]>([])
  const [makerOptions, setMakerOptions] = useState<SelectOption[]>([])
  const [seriesOptions, setSeriesOptions] = useState<SelectOption[]>([])
  const [filtersLoading, setFiltersLoading] = useState(false)
  const [optionsLoaded, setOptionsLoaded] = useState(false)

  const patchForm = useCallback((payload: Partial<MovieFilterState>) => {
    dispatch({ type: 'patch', payload })
  }, [])

  const resetFilters = useCallback(() => {
    dispatch({ type: 'reset' })
  }, [])

  const loadOptions = useCallback(async () => {
    if (!enabled) {
      setOptionsLoaded(false)
      return
    }

    setFiltersLoading(true)
    setOptionsLoaded(false)
    try {
      const shouldLoadActors = isVisible(filterConfig, 'actors') || isVisible(filterConfig, 'actorsNot')
      const shouldLoadTags = isVisible(filterConfig, 'tags') || isVisible(filterConfig, 'tagsNot')
      const shouldLoadDirectors = isVisible(filterConfig, 'director') || isVisible(filterConfig, 'directorNot')
      const shouldLoadMakers = isVisible(filterConfig, 'maker') || isVisible(filterConfig, 'makerNot')
      const shouldLoadSeries = isVisible(filterConfig, 'series') || isVisible(filterConfig, 'seriesNot')

      const [
        tasks,
        actors,
        tags,
        directors,
        makers,
        series,
      ] = await Promise.all([
        getTaskDict(),
        shouldLoadActors ? fetchFilters(MOVIE_FILTER_OPTION_TYPE.ACTOR) : Promise.resolve([]),
        shouldLoadTags ? fetchFilters(MOVIE_FILTER_OPTION_TYPE.TAG) : Promise.resolve([]),
        shouldLoadDirectors ? fetchFilters(MOVIE_FILTER_OPTION_TYPE.DIRECTOR) : Promise.resolve([]),
        shouldLoadMakers ? fetchFilters(MOVIE_FILTER_OPTION_TYPE.MAKER) : Promise.resolve([]),
        shouldLoadSeries ? fetchFilters(MOVIE_FILTER_OPTION_TYPE.SERIES) : Promise.resolve([]),
      ])

      setTaskOptions(tasks.map((task) => ({ value: task.id, label: task.name })))
      setActorOptions(toOptions(actors))
      setTagOptions(toOptions(tags))
      setDirectorOptions(toOptions(directors))
      setMakerOptions(toOptions(makers))
      setSeriesOptions(toOptions(series))
      setOptionsLoaded(true)
    } catch (error: unknown) {
      message.error(getErrorMessage(error))
    } finally {
      setFiltersLoading(false)
    }
  }, [enabled, filterConfig, message])

  useEffect(() => {
    void loadOptions()
  }, [loadOptions])

  const requestParams = useMemo(() => buildMovieFilterParams(form), [form])

  return {
    form,
    patchForm,
    resetFilters,
    requestParams,
    taskOptions,
    actorOptions,
    tagOptions,
    directorOptions,
    makerOptions,
    seriesOptions,
    filtersLoading,
    optionsLoaded,
  }
}

export type MovieFilters = ReturnType<typeof useMovieFilters>
