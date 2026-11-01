import { describe, expect, it } from 'vitest'
import dayjs from 'dayjs'
import { buildMovieFilterDefaultState, buildMovieFilterParams } from '../utils/movieFilter'

describe('Jellyfin watch filter', () => {
  it('maps the selected and configured status to API params', () => {
    const defaults = buildMovieFilterDefaultState({ jellyfinWatchStatus: { visible: true, order: 21, defaultValue: 'played' } })
    expect(defaults.jellyfinWatchStatus).toBe('played')
    expect(buildMovieFilterParams({
      selectedActors: [], selectedActorsNot: [], selectedTags: [], selectedTagsNot: [],
      selectedDirectors: [], selectedDirectorsNot: [], selectedMakers: [], selectedMakersNot: [],
      selectedSeries: [], selectedSeriesNot: [], search: '', storageStatus: undefined,
      scrapingStatus: undefined, jellyfinWatchStatus: 'played',
      releaseDateFrom: null, releaseDateTo: null, createdAtFrom: null, createdAtTo: null,
      jellyfinLastPlayedFrom: null, jellyfinLastPlayedTo: null,
    }).jellyfin_watch_status).toBe('played')
  })

  it('maps configurable last-played date bounds to API params', () => {
    const defaults = buildMovieFilterDefaultState({
      jellyfinLastPlayedFrom: { visible: true, order: 22, defaultValue: '2026-10-01' },
      jellyfinLastPlayedTo: { visible: true, order: 23, defaultValue: '2026-10-31' },
    })
    expect(defaults.jellyfinLastPlayedFrom?.format('YYYY-MM-DD')).toBe('2026-10-01')
    expect(defaults.jellyfinLastPlayedTo?.format('YYYY-MM-DD')).toBe('2026-10-31')

    const params = buildMovieFilterParams({
      selectedActors: [], selectedActorsNot: [], selectedTags: [], selectedTagsNot: [],
      selectedDirectors: [], selectedDirectorsNot: [], selectedMakers: [], selectedMakersNot: [],
      selectedSeries: [], selectedSeriesNot: [], search: '',
      releaseDateFrom: null, releaseDateTo: null, createdAtFrom: null, createdAtTo: null,
      jellyfinLastPlayedFrom: dayjs('2026-10-01'), jellyfinLastPlayedTo: dayjs('2026-10-31'),
    })
    expect(params.jellyfin_last_played_from).toBe('2026-10-01')
    expect(params.jellyfin_last_played_to).toBe('2026-10-31')
  })

  it('does not apply a hidden last-played default', () => {
    const defaults = buildMovieFilterDefaultState({
      jellyfinLastPlayedFrom: { visible: false, order: 22, defaultValue: '2026-10-01' },
    })
    expect(defaults.jellyfinLastPlayedFrom).toBeUndefined()
  })
})
