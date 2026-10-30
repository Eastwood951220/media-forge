import { describe, expect, it } from 'vitest'
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
    }).jellyfin_watch_status).toBe('played')
  })
})
