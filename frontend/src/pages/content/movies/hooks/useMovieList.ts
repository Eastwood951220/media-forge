import {useCallback, useEffect, useRef, useState} from "react";
import type React from "react";
import {App} from "antd";
import {fetchMovies, syncMovieStorageStatus} from "@/api/movie";
import {DEFAULT_MOVIE_PAGE, DEFAULT_MOVIE_PAGE_SIZE, INITIAL_MOVIE_LIST_RESPONSE, DEFAULT_MOVIE_SORT_FIELD, DEFAULT_MOVIE_SORT_ORDER} from "../constants";
import type {Movie, MovieListResponse} from "@/api/movie/types";
import type {MovieFilterParams} from "../utils/movieFilter";

function getErrorMessage(error: unknown): string {
    return error instanceof Error ? error.message : "请求失败";
}

function mergeMovieStorageFields(current: Movie, refreshed: Movie): Movie {
    return {
        ...current,
        storage_status: refreshed.storage_status,
        storage_locations: refreshed.storage_locations,
        storage_summary: refreshed.storage_summary,
    };
}

type MovieListStateCache = {
    filterKey: string;
    page: number;
    pageSize: number;
    sortBy: string;
    sortOrder: number;
}

/** A single `movie.storage.updated` realtime update, batched by the list hook. */
export type MovieStorageUpdate = {
    movie_id: string;
    storage_summary: Record<string, unknown>;
}

const MOVIE_LIST_STATE_CACHE_KEY = "media-forge:movie-list-state";

function readMovieListStateCache(): MovieListStateCache | null {
    if (typeof window === "undefined") return null;
    try {
        const raw = window.sessionStorage.getItem(MOVIE_LIST_STATE_CACHE_KEY);
        return raw ? JSON.parse(raw) as MovieListStateCache : null;
    } catch {
        return null;
    }
}

function writeMovieListStateCache(cache: MovieListStateCache): void {
    if (typeof window === "undefined") return;
    try {
        window.sessionStorage.setItem(MOVIE_LIST_STATE_CACHE_KEY, JSON.stringify(cache));
    } catch {
        // Ignore storage quota/privacy errors; keep-alive still preserves state when available.
    }
}

function cacheMatchesCurrentTaskSearch(cache: MovieListStateCache): boolean {
    if (typeof window === "undefined") return true;
    try {
        const cachedTaskId = (JSON.parse(cache.filterKey) as MovieFilterParams).source_task_id;
        const currentTaskId = new URLSearchParams(window.location.search).get("task_id") ?? undefined;
        return cachedTaskId === currentTaskId;
    } catch {
        return true;
    }
}

export function useMovieList(
    filterParams: MovieFilterParams | undefined,
    initialSort?: { sortBy: string; sortOrder: number },
) {
    const {message} = App.useApp();
    // Read the persisted list state once per mount. It used to be re-read and
    // re-parsed on every render, which dominated renders whenever a cached page
    // carried many rows.
    const [initialCachedState] = useState(() => {
        const cached = readMovieListStateCache();
        return cached && cacheMatchesCurrentTaskSearch(cached) ? cached : null;
    });
    const [data, setData] = useState<MovieListResponse>(INITIAL_MOVIE_LIST_RESPONSE);
    const [page, setPage] = useState(initialCachedState?.page ?? DEFAULT_MOVIE_PAGE);
    const [pageSize, setPageSize] = useState(initialCachedState?.pageSize ?? DEFAULT_MOVIE_PAGE_SIZE);
    const [sortBy, setSortBy] = useState(initialCachedState?.sortBy ?? initialSort?.sortBy ?? DEFAULT_MOVIE_SORT_FIELD);
    const [sortOrder, setSortOrder] = useState<number>(initialCachedState?.sortOrder ?? initialSort?.sortOrder ?? DEFAULT_MOVIE_SORT_ORDER);
    const [loading, setLoading] = useState(false);
    const [syncingStorage, setSyncingStorage] = useState(false);
    const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

    const filterKey = filterParams === undefined ? "__not_ready__" : JSON.stringify(filterParams);
    const previousFilterKeyRef = useRef<string | null>(null);
    const requestSeqRef = useRef(0);

    useEffect(() => {
        if (!filterParams) return;
        // Only pagination/sort metadata is persisted: serializing whole pages
        // (rows, covers, nested data) on every change is what made the page janky.
        writeMovieListStateCache({
            filterKey,
            page,
            pageSize,
            sortBy,
            sortOrder,
        });
    }, [filterKey, filterParams, page, pageSize, sortBy, sortOrder]);

    const loadMovies = useCallback(async () => {
        if (!filterParams) return;
        const requestSeq = ++requestSeqRef.current;
        setLoading(true);
        try {
            const result = await fetchMovies({
                ...filterParams,
                page,
                limit: pageSize,
                sort_by: sortBy,
                sort_order: sortOrder,
            });
            if (requestSeq !== requestSeqRef.current) return;
            setData(result);
        } catch (e: unknown) {
            if (requestSeq !== requestSeqRef.current) return;
            message.error(getErrorMessage(e));
        } finally {
            if (requestSeq === requestSeqRef.current) {
                setLoading(false);
            }
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps -- Fetch identity is filter CONTENT (filterKey), not object identity: filterParams only changes content when filterKey changes, so keying off filterKey keeps identity-only parent rerenders from refetching equal queries.
    }, [filterKey, message, page, pageSize, sortBy, sortOrder]);

    useEffect(() => {
        if (!filterParams) {
            previousFilterKeyRef.current = null;
            return;
        }
        if (previousFilterKeyRef.current === null) {
            previousFilterKeyRef.current = filterKey;
            return;
        }
        if (previousFilterKeyRef.current !== filterKey) {
            previousFilterKeyRef.current = filterKey;
            setSelectedRowKeys([]);
            setPage(DEFAULT_MOVIE_PAGE);
        }
    }, [filterKey, filterParams]);

    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- Initial load on mount/param change is intentional.
        void loadMovies();
    }, [loadMovies]);

    const search = useCallback(() => {
        setSelectedRowKeys([]);
        if (page === DEFAULT_MOVIE_PAGE) {
            void loadMovies();
        } else {
            setPage(DEFAULT_MOVIE_PAGE);
        }
    }, [page, loadMovies]);

    const reload = useCallback(() => {
        setSelectedRowKeys([]);
        void loadMovies();
    }, [loadMovies]);

    const refreshStorageFields = useCallback(async () => {
        if (!filterParams || data.items.length === 0) return;
        const requestSeq = ++requestSeqRef.current;
        try {
            const result = await fetchMovies({
                ...filterParams,
                page,
                limit: pageSize,
                sort_by: sortBy,
                sort_order: sortOrder,
            });
            if (requestSeq !== requestSeqRef.current) return;
            const refreshedById = new Map(result.items.map((movie) => [movie._id, movie]));
            setData((prev) => ({
                ...prev,
                items: prev.items.map((movie) => {
                    const refreshed = refreshedById.get(movie._id);
                    return refreshed ? mergeMovieStorageFields(movie, refreshed) : movie;
                }),
            }));
        } catch (e: unknown) {
            if (requestSeq !== requestSeqRef.current) return;
            message.error(getErrorMessage(e));
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps -- Refresh identity is filter CONTENT (filterKey), not object identity, matching loadMovies above.
    }, [data.items.length, filterKey, message, page, pageSize, sortBy, sortOrder]);

    const handleShowSizeChange = useCallback((_current: number, size: number) => {
        setSelectedRowKeys([]);
        setPageSize(size);
        setPage(DEFAULT_MOVIE_PAGE);
    }, []);

    const handlePageChange = useCallback((nextPage: number, nextPageSize: number) => {
        setSelectedRowKeys([]);
        setPage(nextPage);
        setPageSize(nextPageSize);
    }, []);

    const handleSortChange = useCallback((field: string, order: number) => {
        setSortBy(field);
        setSortOrder(order);
        setPage(DEFAULT_MOVIE_PAGE);
    }, []);

    const resetSort = useCallback((override?: { sortBy: string; sortOrder: number }) => {
        setSortBy(override?.sortBy ?? DEFAULT_MOVIE_SORT_FIELD);
        setSortOrder(override?.sortOrder ?? DEFAULT_MOVIE_SORT_ORDER);
    }, []);

    const applyStorageUpdates = useCallback((updates: MovieStorageUpdate[]) => {
        if (updates.length === 0) return;
        const summariesByMovie = new Map<string, Record<string, unknown>[]>();
        for (const update of updates) {
            const summaries = summariesByMovie.get(update.movie_id);
            if (summaries) {
                summaries.push(update.storage_summary);
            } else {
                summariesByMovie.set(update.movie_id, [update.storage_summary]);
            }
        }
        setData((prev) => ({
            ...prev,
            items: prev.items.map((item) => {
                const summaries = summariesByMovie.get(item._id);
                if (!summaries) return item;
                // Fold in arrival order so a batched burst matches the
                // per-event updates it replaces.
                return summaries.reduce<Movie>((movie, summary) => ({
                    ...movie,
                    storage_status: String(summary.storage_status || 'not_stored') as Movie['storage_status'],
                    storage_summary: {
                        ...movie.storage_summary,
                        ...summary,
                    },
                }), item);
            }),
        }));
    }, []);

    const applyScrapingUpdates = useCallback(
        (updates: Array<{ movie_id: string; scraping_status: Movie['scraping_status']; scraping_checked_at?: string | null }>) => {
            if (updates.length === 0) return;
            const byId = new Map(updates.map((update) => [update.movie_id, update]));
            setData((current) => ({
                ...current,
                items: current.items.map((item) => {
                    const update = byId.get(item._id);
                    if (!update) return item;
                    return {
                        ...item,
                        scraping_status: update.scraping_status,
                        scraping_checked_at: update.scraping_checked_at ?? item.scraping_checked_at,
                    };
                }),
            }));
        },
        [],
    );

    const syncStorageStatus = useCallback(async () => {
        if (!filterParams) return;
        setSyncingStorage(true);
        try {
            const selectedIds = selectedRowKeys.map((key) => String(key));
            const payload = selectedIds.length > 0
                ? {movie_ids: selectedIds}
                : {filters: filterParams};
            const result = await syncMovieStorageStatus(payload);
            message.success(`同步完成：已存储 ${result.stored_count} 条，未存储 ${result.not_stored_count} 条`);
            setSelectedRowKeys([]);
            await loadMovies();
        } catch (e: unknown) {
            message.error(getErrorMessage(e));
        } finally {
            setSyncingStorage(false);
        }
    }, [filterParams, loadMovies, message, selectedRowKeys]);

    return {
        data, page, pageSize, sortBy, sortOrder, loading, syncingStorage, selectedRowKeys,
        setPage, setPageSize, setSelectedRowKeys,
        search, reload, refreshStorageFields, syncStorageStatus, handlePageChange, handleShowSizeChange, handleSortChange, resetSort, applyStorageUpdates, applyScrapingUpdates,
    };
}

export type MovieList = ReturnType<typeof useMovieList>;
