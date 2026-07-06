import { DEFAULT_MOVIE_PAGE } from '../constants'
import type { MovieFilterState } from './movieFilter'

const fieldMap: Record<string, keyof MovieFilterState> = {
  director: 'selectedDirectors',
  maker: 'selectedMakers',
  series: 'selectedSeries',
  actors: 'selectedActors',
  tags: 'selectedTags',
}

export function applyDetailFilterClick({
  closeDetail,
  field,
  form,
  patchForm,
  setPage,
  value,
}: {
  closeDetail: () => void
  field: string
  form: Partial<MovieFilterState>
  patchForm: (patch: Partial<MovieFilterState>) => void
  setPage: (page: number) => void
  value: string
}) {
  closeDetail()
  const stateKey = fieldMap[field]
  if (!stateKey) return
  const current = (form[stateKey] as string[]) || []
  if (!current.includes(value)) {
    patchForm({ [stateKey]: [...current, value] } as Partial<MovieFilterState>)
  }
  setPage(DEFAULT_MOVIE_PAGE)
}
