import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MovieListPage from '../MovieListPage'

const baseListPageMock = vi.hoisted(() => ({
  props: undefined as { columnSettingsKey?: string } | undefined,
}))

vi.mock('@/components/BaseListPage', () => ({
  default: (props: { columnSettingsKey?: string }) => {
    baseListPageMock.props = props
    return <div>BaseListPage mock</div>
  },
}))

vi.mock('../hooks/useMovieFilterConfig', () => ({
  useMovieFilterConfig: () => ({
    config: {},
    loaded: true,
    loading: false,
    drawerOpen: false,
    setDrawerOpen: vi.fn(),
    setConfig: vi.fn(),
  }),
}))

vi.mock('../hooks/useMovieFilters', () => ({
  useMovieFilters: () => ({
    optionsLoaded: true,
    filtersLoading: false,
    requestParams: {},
    search: vi.fn(),
    form: { selectedTask: undefined },
  }),
}))

vi.mock('../hooks/useMovieList', () => ({
  useMovieList: () => ({
    data: { items: [], total: 0 },
    loading: false,
    selectedRowKeys: [],
    setSelectedRowKeys: vi.fn(),
    page: 1,
    pageSize: 20,
    sortBy: 'created_at',
    sortOrder: 'desc',
    handleSortChange: vi.fn(),
    handlePageChange: vi.fn(),
    reload: vi.fn(),
    resetSort: vi.fn(),
    syncingStorage: false,
    syncStorageStatus: vi.fn(),
    updateMovie: vi.fn(),
  }),
}))

vi.mock('../hooks/useMovieDetail', () => ({
  useMovieDetail: () => ({
    open: false,
    detail: null,
    showDetail: vi.fn(),
    closeDetail: vi.fn(),
  }),
}))

vi.mock('../hooks/useMovieListActions', () => ({
  useMovieListActions: () => ({
    confirmDeleteMovies: vi.fn(),
    refreshMagnetsForMovies: vi.fn(),
    handleResetFilters: vi.fn(),
    handleBulkPush: vi.fn(),
    handleBatchDelete: vi.fn(),
    handleBulkRefreshMagnets: vi.fn(),
    handleDetailFilterClick: vi.fn(),
  }),
}))

vi.mock('../hooks/useMovieStorageIndexActions', () => ({
  useMovieStorageIndexActions: () => ({
    handleCd2Sync: vi.fn(),
    cd2SyncingId: null,
    handleRefreshStorageIndex: vi.fn(),
    indexRefreshing: null,
  }),
}))

vi.mock('../hooks/useStoragePush', () => ({
  useStoragePush: () => ({
    openSinglePush: vi.fn(),
    modalOpen: false,
    pushMode: 'single',
    pushMovies: [],
    selectedKeys: [],
    submitting: false,
    defaultAlias: '',
    closeModal: vi.fn(),
    submitPush: vi.fn(),
  }),
}))

vi.mock('../hooks/useMoviePageSortDefault', () => ({
  useMoviePageSortDefault: vi.fn(),
}))

vi.mock('../hooks/useMovieUrlDetail', () => ({
  useMovieUrlDetail: vi.fn(),
}))

vi.mock('../hooks/useMovieListRealtime', () => ({
  useMovieListRealtime: vi.fn(),
}))

vi.mock('../components/MovieFilterBar', () => ({
  default: () => <div>MovieFilterBar mock</div>,
}))

vi.mock('../components/MovieDetailDrawer', () => ({
  default: () => null,
}))

vi.mock('../components/FilterConfigDrawer', () => ({
  default: () => null,
}))

vi.mock('../components/StoragePushModal', () => ({
  default: () => null,
}))

describe('MovieListPage column settings', () => {
  beforeEach(() => {
    baseListPageMock.props = undefined
  })

  it('enables persisted column settings for the movie list', () => {
    render(<MovieListPage />)

    expect(screen.getByText('BaseListPage mock')).toBeInTheDocument()
    expect(baseListPageMock.props?.columnSettingsKey).toBe('content.movies')
  })
})
